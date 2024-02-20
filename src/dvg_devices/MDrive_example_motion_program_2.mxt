'[VARIABLES]

' Flash with Novanta IMS Motion Terminal
' Remember to set "Py = 1" afterwards
' and to save to controller NVM with "2s"
Dn = "2"
Vi = 1000
Vm = 25600
A = 1000000
D = 1000000
Rc = 75
Hc = 25
S1 = 3,0,0
S2 = 0,0,0

VA C0 = 6400      'calibration: steps per mm
VA V1 = 51200     'v_abs_max
VA V2 = 2560      'steps jog+ button
VA V3 = -2560     'steps jog- button
VA H1 = 0         'UNKNOWN
VA H2 = 2000      '"Speed" potmeter factor
VA LH = 3         'limit_mode_minus, 0: no limit switch
VA LP = 0         'limit_mode_plus , 0: no limit switch
VA P1 = 0         'max_position    , 0: no max position

'[PROGRAMS]

PG 100
LB SU             '--- Start-up routine
  P = P1
  CL MM
  S3 = 0, 1
  S4 = 0, 1
  S5 = 9

LB M0             '--- Main loop
  BR M0, P1 = 0
  BR M0, V >=0
  BR M0, P > P1
  SL 0
  Er = 83
  BR M0

LB MM             '--- Sub: Set S1 & S2
  S1 = LH, 0
  S2 = LP, 0
  RT 

LB F1             '--- Init interface
  SL 0            'Stop any movement
  BR M0           'Goto: Main loop

LB U9             '--- Idle loop
  H 1
  BR U9
  E 

LB F2             '--- Home
  CL F9           'Call: Home
  BR M0           'Goto: Main loop

LB F7             '--- Step minus
  MR V3           'Move relative
  BR M0           'Goto: Main loop

LB F8             '--- Step plus
  MR V2           'Move relative
  BR M0           'Goto: Main loop

LB F9             '--- Sub: Home
  SL 0            'Stop any movement
  H               'Wait for movement to finish
  BR FH, LH = 0   'Return when no limit- switch is set
  CL Mm           'Call sub: Set S1 & S2
  S1 = 1, 0       'Why?! Don't understand
  HM 1            'Home using method 1
  H               'Wait for movement to finish
  R1 = P & 1023
  R2 = 1024 - R1
  CL Mm           'Call sub: Set S1 & S2
  MR R2           'Move tiny amount away from home again
  H               'Wait for movement to finish
  P = 0           'Redefine position to == 0

LB FH
  RT              'Return

PG
'[END]
