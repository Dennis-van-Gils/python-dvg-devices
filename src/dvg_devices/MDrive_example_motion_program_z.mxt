'HOWTO flash this program onto the MDrive using Novanta IMS Motion Terminal.
'Connect one motor at a time and follow these steps.
'1: File->Open and select the .mxt file. This opens a new 'Editor' window.
'2: Set up serial connection to the MDrive (File->New Terminal) and connect.
'3: Press [Esc] within the terminal to get a prompt, either ">", "?" or empty.
'4: We are going to reset the MDrive to factory defaults.
'   When the MDrive is not in party mode: Enter command "FD".
'   When the MDrive is in party mode: Enter command "*FD". Press [Ctrl]+[J].
'   The MDrive should respond with a copyright notice when successful.
'   When having problems resetting the MDrive, follow the guide at
'   https://www.novantaims.com/application-note/units-stuck-party-mode-checksum-mode/
'   FD reset: ^MFD^M ^d1000 ^MCK=0…^M ^d1000 ^J*FD^J^d1000^J*FDÌ^J
'5: Transfer->Download->From ###.mxt file.
'6: Tick 'Variables' and 'Programs', leave 'Device name' empty.
'7: Click 'Download'.
'8: Enter command "PY 1" to set the MDrive into party mode. Press [Ctrl]+[J].
'9: Enter command "[Dn]S" to save the new variables and programs to the MDrive
'   flash memory. Replace [Dn] with the device name character. Press [Ctrl]+[J].
'10: Close serial connection. Done.

'[VARIABLES]

Dn = "z"          'Device name
Em = 0            'Echo mode: 0 = Full duplex
Vi = 1280         'Initial velocity
Vm = 25600        'Maximum velocity
A = 128000        'Acceleration
D = 128000        'Deceleration

'Look up from motor spec sheet
Rc = 75           'Motor run current
Hc = 25           'Motor holding current

'Specific to Python interface:
'https://github.com/Dennis-van-Gils/python-dvg-devices
VA CT = 0         'Movement type: 0 = linear, 1 = angular
VA C0 = 6400      'Steps per mm (linear) or steps per revolution (angular)

'Limit switches
VA L1 = 3         'Input type for switch S1, 0: no switch
VA L2 = 0         'Input type for switch S2, 0: no switch
S1 = L1, 0, 0
S2 = L2, 0, 0
S3 = 0, 1, 0
S4 = 0, 1, 0
Lm = 4            'Limit stop mode

'[PROGRAMS]

PG 100
LB SU             '--- Start-up routine
  P = 0
  CL MM

LB M0             '--- Main loop
  BR M0

LB Mm             '--- Sub: (Re)set limit switches
  S1 = L1, 0, 0
  S2 = L2, 0, 0
  RT

LB F1             '--- Init interface
  SL 0            'Stop any movement
  H               'Wait for movement to finish
  BR M0           'Goto: Main loop

LB F2             '--- Home
  SL 0            'Stop any movement
  H               'Wait for movement to finish
  BR Fh, L1 = 0   'Return when no switch is set
  S1 = 1, 0, 0    'Ensure S1 is set as homing switch
  HM 1            'Home using method 1
  H               'Wait for movement to finish
  R1 = P & 1023
  R2 = 1024 - R1
  MR R2           'Move tiny amount away from home again
  H               'Wait for movement to finish
  P = 0           'Redefine position to == 0
  CL Mm
  BR M0           'Goto: Main loop

LB FH
  RT              'Return

PG
'[END]
