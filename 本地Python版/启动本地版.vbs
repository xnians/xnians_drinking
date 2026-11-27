' 咕咚校园 本地版 —— 无黑窗启动（推荐双击这个）
' 自动定位本文件所在目录，用 pythonw 后台运行，不弹黑色命令行窗口。
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = strDir
WshShell.Run "pythonw """ & strDir & "\drink_local.py""", 0, False
