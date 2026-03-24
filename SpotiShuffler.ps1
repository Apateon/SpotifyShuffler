$ProjectPath = "C:\Users\marsh\Desktop\SpotifyShuffler"
$PythonExe = "$ProjectPath\.venv\Scripts\pythonw.exe"
$ScriptFile = "SpotiShuffler.py"

$Process = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" | Where-Object { $_.CommandLine -like "*$ScriptFile*" }

if ($Process -and $Process.ProcessID -gt 0)
{
	Stop-Process -Id $Process.ProcessId -Force
	Add-Type -AssemblyName System.Windows.Forms
	[System.Windows.Forms.MessageBox]::Show("Server Stopped", "Spotify Shuffler")
}
else
{
	if (Test-Path $PythonExe)
	{
		Set-Location $ProjectPath
		Start-Process -FilePath $PythonExe -ArgumentList $ScriptFile -WindowStyle Hidden
	}
	else
	{
		Add-Type -AssemblyName System.Windows.Forms
		[System.Windows.Forms.MessageBox]::Show("Error: Could not find Python at $PythonExe", "Spotify Shuffler")
	}
}