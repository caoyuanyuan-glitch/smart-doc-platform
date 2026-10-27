Option Explicit

' Chinese-named shortcut. Real launcher is start_extractor.vbs.

Dim fso, shell, scriptDir, target
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = fso.BuildPath(scriptDir, "start_extractor.vbs")

If Not fso.FileExists(target) Then
  MsgBox "Missing start_extractor.vbs." & vbCrLf & vbCrLf & _
         "Keep the whole folder together. Prefer 打开审核意见汇总工具.hta if VBS is blocked.", _
         16, "Review Comment Extractor"
  WScript.Quit 1
End If

shell.Run "wscript.exe " & """" & target & """", 1, False
