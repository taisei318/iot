# receiver.pyの実行方法

**windowsの場合**
1. spresenseと繋がっているポートを確認する.
``` bash
Get-WmiObject Win32_SerialPort | Select-Object Name, DeviceID
```

2. 実行する（1の結果がCOM7の場合）
``` bash
python3 .\raspi\receiver.py --port COM7
```