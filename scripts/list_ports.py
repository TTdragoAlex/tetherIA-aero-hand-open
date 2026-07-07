from serial.tools import list_ports

ports = list(list_ports.comports())
if not ports:
    print('No serial ports found.')
    raise SystemExit(0)

for port in ports:
    print(f'{port.device}\t{port.description}\t{port.hwid}')
