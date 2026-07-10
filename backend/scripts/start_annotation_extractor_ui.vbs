Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir

shell.Run "pyw.exe """ & scriptDir & "\annotation_extractor_ui.pyw""", 0, False
