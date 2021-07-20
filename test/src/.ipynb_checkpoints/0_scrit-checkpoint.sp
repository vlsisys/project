* ====================================================================
* Author :	Woong Choi, woongchoi@sm.ac.kr
* 		Sookmyung Women's Univ, VLSISYS Lab.
* ====================================================================
.title	'SMU, VLSISYS Lab.'
.option	post
.option	probe
.option	measdgt = 6
.option	numdgt = 6
.option	ingold
.option	modmonte = 1
.option	mtthred = 2
.option	measform = 3
.option	mcbrief = 2
.option	abstol=1e-6 reltol=1e-6
*.option ba_file = ""

* --------------------------------------------------------------------
* [ PVT MODEL ]
* --------------------------------------------------------------------
.lib	'{SIM_LIB}' {SIM_PVT_P}

.param	p_vdd	= {SIM_PVT_V}
.param	p_vss	= 0
.temp	{SIM_PVT_T}

* --------------------------------------------------------------------
* [ Include Files]
* --------------------------------------------------------------------
.inc	'{SIM_NET}'

* --------------------------------------------------------------------
* [ Vth Params ]
* --------------------------------------------------------------------
.param	dvt_pul	= '-sigval*vtsig_pu'
.param	dvt_pur	= '+sigval*vtsig_pu'
.param	dvt_pgl	= '-sigval*vtsig_pg'
.param	dvt_pgr	= '+sigval*vtsig_pg'
.param	dvt_pdl	= '+sigval*vtsig_pd'
.param	dvt_pdr	= '-sigval*vtsig_pd'

.param	vtsig_pu = {SIM_VTSIG_PU}
.param	vtsig_pg = {SIM_VTSIG_PU}
.param	vtsig_pd = {SIM_VTSIG_PU}

* --------------------------------------------------------------------
* [ Circuit Description ]
* --------------------------------------------------------------------
.param	ast_vbs = {SIM_AST_VBS}
.param	ast_wlu = {SIM_AST_WLU}
.param	ast_sbl = {SIM_AST_SBL}
.param	p_vcrit	= 0

vvdd	vdd	0	'p_vdd*ast_vbs'
vvss	vss	0	p_vss

vcrit	q	0	p_vcrit

.nodeset	v(q)	p_vss
.nodeset	v(qb)	p_vdd

vwl		wl		0	'p_vdd*ast_wlu'
vblt	blt		0	'p_vdd*ast_sbl'
vblb	blb		0	'p_vdd*ast_sbl'

* --------------------------------------------------------------------
* [ Step1	]
* --------------------------------------------------------------------
.model	optmod opt method = bisection Relin = 1e-4 itropt=100
.param	sigval = opt1 (0, 0, 10)
.dc		p_vcrit	0	p_vdd	0.001	sweep optimize = opt1 result = icrit model = optmod
.meas	icrit		max par('-i(vcrit)') from = 0 to = 'p_vdd/2' goal = 0
.meas	vflip		find		v(qb)	when v(qb) = v(q)
.meas	v0			find		v(q)	when par('-i(vcrit)') = 0 rise = 1
.meas	vtrip		find		v(q)	when v(q) = v(qb)

*.dc		p_vcrit	0	p_vdd	0.001	
*.meas	icrit		max par('-i(vcrit)') from = 0 to = 'p_vdd/2' goal = 0

.probe	v(*)
.probe	i(*)

.end