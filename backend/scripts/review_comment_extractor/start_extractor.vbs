Option Explicit

' Launch the GUI with pythonw. Do not call powershell.exe or python.exe.
' Hidden pythonw must be probed first: a leftover pyw.exe would otherwise
' exit immediately and look like "VBS did nothing".

Const WINDOW_HIDDEN = 0

Dim fso, shell, scriptDir, pywScript, pythonw, launchLog
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir
pywScript = fso.BuildPath(scriptDir, "annotation_extractor.pyw")
launchLog = fso.BuildPath(scriptDir, "annotation_extractor_launch.log")

InitLaunchLog
LogLine "VBS started: " & WScript.ScriptFullName

If Not fso.FileExists(pywScript) Then
  Fail "Missing annotation_extractor.pyw." & vbCrLf & vbCrLf & _
       "Keep this VBS file in the same folder as annotation_extractor.pyw."
End If

pythonw = FindWorkingPythonW()
If pythonw = "" Then
  Fail "pythonw.exe was not found, or it cannot open a GUI (tkinter)." & vbCrLf & vbCrLf & _
       "Install Python 3 from https://www.python.org/downloads/" & vbCrLf & _
       "During setup, tick: Add python.exe to PATH" & vbCrLf & _
       "Do not use the Microsoft Store Python stub." & vbCrLf & vbCrLf & _
       "After install, open cmd.exe and run:" & vbCrLf & _
       "py -m pip install PyMuPDF" & vbCrLf & vbCrLf & _
       "If this VBS still does nothing, double-click:" & vbCrLf & _
       "  打开审核意见汇总工具.hta" & vbCrLf & _
       "  or start_extractor.cmd" & vbCrLf & vbCrLf & _
       "Log: " & launchLog
End If

LogLine "run " & pythonw & " " & pywScript
On Error Resume Next
Err.Clear
shell.Run Quote(pythonw) & " " & Quote(pywScript), WINDOW_HIDDEN, False
If Err.Number <> 0 Then
  Fail "Failed to start pythonw.exe" & vbCrLf & pythonw & vbCrLf & Err.Description & vbCrLf & vbCrLf & "Log: " & launchLog
End If
On Error GoTo 0
LogLine "pythonw dispatched"
WScript.Quit 0

Sub InitLaunchLog
  Dim ts
  On Error Resume Next
  Set ts = fso.OpenTextFile(launchLog, 2, True)
  If Err.Number = 0 Then
    ts.WriteLine Now & " ---- launch log ----"
    ts.Close
  End If
  On Error GoTo 0
End Sub

Sub LogLine(text)
  Dim ts
  On Error Resume Next
  Set ts = fso.OpenTextFile(launchLog, 8, True)
  If Err.Number = 0 Then
    ts.WriteLine Now & " " & text
    ts.Close
  End If
  On Error GoTo 0
End Sub

Sub Fail(text)
  LogLine "FAIL " & Replace(text, vbCrLf, " | ")
  MsgBox text, 16, "Review Comment Extractor"
  WScript.Quit 1
End Sub

Function Quote(text)
  Quote = """" & text & """"
End Function

Function IsStoreStub(path)
  Dim lower
  lower = LCase(path)
  IsStoreStub = (InStr(lower, "\windowsapps\") > 0)
End Function

Function FileIfExists(path)
  If path <> "" Then
    If fso.FileExists(path) And Not IsStoreStub(path) Then
      FileIfExists = path
      Exit Function
    End If
  End If
  FileIfExists = ""
End Function

Sub AddCandidate(dict, path)
  Dim full
  full = FileIfExists(path)
  If full <> "" Then
    If Not dict.Exists(LCase(full)) Then
      dict.Add LCase(full), full
      LogLine "candidate " & full
    End If
  End If
End Sub

Sub AddWhich(dict, exeName)
  Dim pathEnv, dirs, i
  pathEnv = shell.ExpandEnvironmentStrings("%PATH%")
  dirs = Split(pathEnv, ";")
  For i = 0 To UBound(dirs)
    If Trim(dirs(i)) <> "" Then
      AddCandidate dict, fso.BuildPath(Trim(dirs(i)), exeName)
    End If
  Next
End Sub

Sub AddRegistry(dict)
  Dim roots, versions, r, v, installDir
  roots = Array( _
    "HKCU\Software\Python\PythonCore\", _
    "HKLM\Software\Python\PythonCore\", _
    "HKLM\Software\Wow6432Node\Python\PythonCore\" _
  )
  versions = Array("3.14", "3.13", "3.12", "3.11", "3.10", "3.9", "3.8")
  On Error Resume Next
  For Each r In roots
    For Each v In versions
      Err.Clear
      installDir = shell.RegRead(r & v & "\InstallPath\")
      If Err.Number = 0 Then
        AddCandidate dict, fso.BuildPath(installDir, "pythonw.exe")
      End If
    Next
  Next
  On Error GoTo 0
End Sub

Sub AddLocalPrograms(dict)
  Dim programs, subf
  programs = fso.BuildPath(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%"), "Programs\Python")
  If fso.FolderExists(programs) Then
    For Each subf In fso.GetFolder(programs).SubFolders
      AddCandidate dict, fso.BuildPath(subf.Path, "pythonw.exe")
    Next
  End If
End Sub

Sub AddCommonFolders(dict)
  Dim home, extras, i
  home = shell.ExpandEnvironmentStrings("%USERPROFILE%")
  extras = Array( _
    fso.BuildPath(home, "anaconda3\pythonw.exe"), _
    fso.BuildPath(home, "miniconda3\pythonw.exe"), _
    fso.BuildPath(home, "AppData\Local\anaconda3\pythonw.exe"), _
    "C:\Python314\pythonw.exe", _
    "C:\Python313\pythonw.exe", _
    "C:\Python312\pythonw.exe", _
    "C:\Python311\pythonw.exe", _
    "C:\Python310\pythonw.exe" _
  )
  For i = 0 To UBound(extras)
    AddCandidate dict, extras(i)
  Next
End Sub

Function PythonWorks(pythonwPath)
  Dim rc
  On Error Resume Next
  Err.Clear
  rc = shell.Run(Quote(pythonwPath) & " -c ""import tkinter""", WINDOW_HIDDEN, True)
  If Err.Number <> 0 Then
    LogLine "probe error " & Err.Number & " " & Err.Description & " " & pythonwPath
    PythonWorks = False
    Exit Function
  End If
  LogLine "probe rc=" & rc & " " & pythonwPath
  PythonWorks = (rc = 0)
End Function

Function FindWorkingPythonW()
  Dim dict, k, p
  Set dict = CreateObject("Scripting.Dictionary")
  AddRegistry dict
  AddLocalPrograms dict
  AddCommonFolders dict
  AddWhich dict, "pythonw.exe"
  AddWhich dict, "pyw.exe"
  AddCandidate dict, fso.BuildPath(shell.ExpandEnvironmentStrings("%SystemRoot%"), "pyw.exe")
  For Each k In dict.Keys
    p = dict(k)
    If PythonWorks(p) Then
      LogLine "selected " & p
      FindWorkingPythonW = p
      Exit Function
    End If
  Next
  FindWorkingPythonW = ""
End Function
