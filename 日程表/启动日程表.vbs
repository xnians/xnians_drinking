' Schedule app launcher - runs without a console window.
' All paths are resolved from this script's own folder, so the project can be
' moved or copied to another machine without editing anything.
Option Explicit
Dim fso, sh, base
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base

On Error Resume Next
sh.Run "pythonw.exe """ & base & "\app.py""", 0, False
If Err.Number = 0 Then WScript.Quit 0
Err.Clear

sh.Run """" & sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & _
       "\Programs\Python\Python313\pythonw.exe"" """ & base & "\app.py""", 0, False
If Err.Number = 0 Then WScript.Quit 0
Err.Clear

MsgBox "pythonw.exe not found." & vbCrLf & vbCrLf & _
       "Please install Python 3.8+ with 'Add Python to PATH'," & vbCrLf & _
       "or run launcher .bat instead.", vbExclamation, "Schedule"
