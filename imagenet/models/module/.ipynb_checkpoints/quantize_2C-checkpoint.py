from collections import namedtuple
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd.function import InplaceFunction, Function
import pdb

QParams = namedtuple('QParams', ['range', 'zero_point', 'num_bits'])

_DEFAULT_FLATTEN = (1, -1)
_DEFAULT_FLATTEN_GRAD = (0, -1)

def _deflatten_as(x, x_full):
    shape = list(x.shape) + [1] * (x_full.dim() - x.dim())
    return x.view(*shape)

def calculate_qparams(x, num_bits, flatten_dims=_DEFAULT_FLATTEN, reduce_dim=0,  reduce_type=None, keepdim=False, true_zero=False):
    
    if x.min() < 0 :
        reduce_dim = None

    with torch.no_grad():
        x_flat = x.flatten(*flatten_dims)
        if x_flat.dim() == 1:
            min_values = _deflatten_as(x_flat.min(), x)
            max_values = _deflatten_as(x_flat.max(), x)
        else:
            min_values = _deflatten_as(x_flat.min(-1)[0], x)
            max_values = _deflatten_as(x_flat.max(-1)[0], x)
        if reduce_dim is not None:  # input
            if reduce_type == 'mean':
                min_values = min_values.mean(reduce_dim, keepdim=keepdim)
                max_values = max_values.mean(reduce_dim, keepdim=keepdim)
            else:
                min_values = min_values.min(reduce_dim, keepdim=keepdim)[0]
                max_values = max_values.max(reduce_dim, keepdim=keepdim)[0]
        # TODO: re-add true zero computation
        
#         range_values = max_values - min_values
        if reduce_dim is not None:
            range_values = torch.where(max_values.abs() > min_values.abs(), max_values.abs(), min_values.abs())
        else:
            range_values = torch.where(max_values.abs() > min_values.abs(), max_values.abs(), min_values.abs())*2
            
        return QParams(range=range_values, zero_point=torch.where(max_values.abs() > min_values.abs(), max_values.abs(), min_values.abs()),
                       num_bits=num_bits)

class UniformQuantize(InplaceFunction):

    @staticmethod
    def forward(ctx, input, num_bits=None, qparams=None, flatten_dims=_DEFAULT_FLATTEN,
                reduce_dim=0, dequantize=True, signed=False, stochastic=False, inplace=False):
        
        if input.min() < 0 :
            signed = True

        ctx.inplace = inplace

        if ctx.inplace:
            ctx.mark_dirty(input)
            output = input
        else:
            output = input.clone()

        if qparams is None:
            assert num_bits is not None, "either provide qparams of num_bits to quantize"
            qparams = calculate_qparams(
                input, num_bits=num_bits, flatten_dims=flatten_dims, reduce_dim=reduce_dim)

        zero_point = qparams.zero_point
        num_bits = qparams.num_bits
        
        qmin = -(2.**(num_bits - 1))+1 if signed else 0.
        qmax = qmin -1 + 2.**num_bits - 1 if signed else 2.**num_bits - 1.
        scale = qparams.range / (qmax - qmin)
        
#         pdb.set_trace()
        
        with torch.no_grad():
            if signed:
#                 output.add_(zero_point).div_(scale)
                output.add_(zero_point)
                output.div_(scale)
                output.clamp_(0, 2*qmax).round_().add_(-1*qmax)
            else:
                output.div_(scale)
                output.clamp_(qmin, qmax).round_()
        
#         qmin = -(2.**(num_bits - 1)) if signed else 0.
#         qmax = qmin + 2.**num_bits - 1.
#         scale = qparams.range / (qmax - qmin)
#         with torch.no_grad():
#             output.add_(qmin * scale - zero_point).div_(scale)
#             if stochastic:
#                 noise = output.new(output.shape).uniform_(-0.5, 0.5)
#                 output.add_(noise)
#             # quantize
#             output.clamp_(qmin, qmax).round_()

            if dequantize:
                output.mul_(scale)
#                 output.mul_(scale).add_(
#                     zero_point - qmin * scale)  # dequantize
        return output

    @staticmethod
    def backward(ctx, grad_output):
        # straight-through estimator
        grad_input = grad_output
        return grad_input, None, None, None, None, None, None, None, None


def quantize(x, num_bits=None, qparams=None, flatten_dims=_DEFAULT_FLATTEN, reduce_dim=0, dequantize=True, signed=False, stochastic=False, inplace=False):
    return UniformQuantize().apply(x, num_bits, qparams, flatten_dims, reduce_dim, dequantize, signed, stochastic, inplace)

class QuantMeasure(nn.Module):
    """docstring for QuantMeasure."""

    def __init__(self, num_bits=8, shape_measure=(1,), flatten_dims=_DEFAULT_FLATTEN,
                 inplace=False, dequantize=True, stochastic=False, momentum=0.1, measure=False):
        super(QuantMeasure, self).__init__()
        self.register_buffer('running_zero_point', torch.zeros(*shape_measure))
        self.register_buffer('running_range', torch.zeros(*shape_measure))
        self.measure = measure
        if self.measure:
            self.register_buffer('num_measured', torch.zeros(1))
        self.flatten_dims = flatten_dims
        self.momentum = momentum
        self.dequantize = dequantize
        self.stochastic = stochastic
        self.inplace = inplace
        self.num_bits = num_bits

    def forward(self, input, qparams=None):

        if self.training or self.measure:
            if qparams is None:
                qparams = calculate_qparams(
                    input, num_bits=self.num_bits, flatten_dims=self.flatten_dims, reduce_dim=0)
            with torch.no_grad():
                if self.measure:
                    momentum = self.num_measured / (self.num_measured + 1)
                    self.num_measured += 1
                else:
                    momentum = self.momentum
                
#                 print('input', input.size())
#                 print('rzp',self.running_zero_point)
#                 print('rzp',self.running_zero_point.size())
#                 print('rra',self.running_range)
#                 print('rra',self.running_range.size())
#                 print('momentum', momentum)
                
#                 print('qparam_zp',qparams.zero_point.size())
#                 print('qparam_zp',qparams.zero_point)
#                 print('qparam_ra',qparams.range.size())
                
                self.running_zero_point.mul_(momentum).add_(qparams.zero_point * (1 - momentum))
                self.running_range.mul_(momentum).add_(qparams.range * (1 - momentum))
        else:
            qparams = QParams(range=self.running_range,
                              zero_point=self.running_zero_point, num_bits=self.num_bits)
        if self.measure:
            return input
        else:
            q_input = quantize(input, qparams=qparams, dequantize=self.dequantize,
                               stochastic=self.stochastic, inplace=self.inplace)
            return q_input



class QConv2d(nn.Conv2d):
    """docstring for QConv2d."""

    def __init__(self, in_channels, out_channels, kernel_size,
                 stride=1, padding=0, dilation=1, groups=1, bias=False, num_bits=8, num_bits_weight=8):
        super(QConv2d, self).__init__(in_channels, out_channels, kernel_size,
                                      stride, padding, dilation, groups, bias)
        self.num_bits = num_bits
        self.num_bits_weight = num_bits_weight or num_bits
        self.quantize_input = QuantMeasure(
            self.num_bits, shape_measure=(1, 1, 1, 1), flatten_dims=(1, -1))
  
    def forward(self, input):
#         pdb.set_trace()
        qinput = self.quantize_input(input)
        weight_qparams = calculate_qparams(
            self.weight, num_bits=self.num_bits_weight, flatten_dims=(1, -1), reduce_dim=None)
        qweight = quantize(self.weight, qparams=weight_qparams)

        if self.bias is not None: 
            qbias = quantize(
                self.bias, num_bits=32,
                flatten_dims=(0, -1))
        else:
            qbias = None
            
        return F.conv2d(qinput, qweight, qbias, self.stride,
                              self.padding, self.dilation, self.groups)
       

class QLinear(nn.Linear):
    """docstring for QConv2d."""

    def __init__(self, in_features, out_features, bias=True, num_bits=8, num_bits_weight=8):
        super(QLinear, self).__init__(in_features, out_features, bias)
        self.num_bits = num_bits
        self.num_bits_weight = num_bits_weight or num_bits
        self.quantize_input = QuantMeasure(self.num_bits)

    def forward(self, input):
#         print(self.num_bits_weight)
        qinput = self.quantize_input(input)
        weight_qparams = calculate_qparams(
            self.weight, num_bits=self.num_bits_weight, flatten_dims=(1, -1), reduce_dim=None)
        qweight = quantize(self.weight, qparams=weight_qparams)
        if self.bias is not None:
            qbias = quantize(
                self.bias, num_bits=self.num_bits_weight + self.num_bits,
                flatten_dims=(0, -1))
        else:
            qbias = None
        return F.linear(qinput, qweight, qbias)

