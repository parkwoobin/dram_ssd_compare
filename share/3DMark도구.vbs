' 3DMark 도구 실행 (콘솔창 없이 백그라운드로)
' 더블클릭하면 gpu_tool.pyw 를 pythonw 로 실행합니다.
Set sh = CreateObject("WScript.Shell")
base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.Run "pythonw """ & base & "gpu_tool.pyw""", 0, False
