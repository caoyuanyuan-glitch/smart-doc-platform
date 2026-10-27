Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
kitDir = fso.BuildPath(scriptDir, "review_comment_extractor")
vbs = fso.BuildPath(kitDir, "打开审核意见汇总工具.vbs")
If fso.FileExists(vbs) Then
  shell.CurrentDirectory = kitDir
  shell.Run "wscript.exe """ & vbs & """", 0, False
Else
  MsgBox "Missing review_comment_extractor\打开审核意见汇总工具.vbs", 16, "Review Comment Extractor"
End If
