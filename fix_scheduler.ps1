# 重建定时任务: 开机启动 + 每小时 + 错过补跑
$name = "WorldCupOddsFetch"
$script = "C:\Users\shish\github-repos\worldcup-2026\run_fetch.bat"

# Delete old
schtasks /delete /tn $name /f 2>$null

# Create with startup trigger
schtasks /create /tn $name /tr $script /sc onstart /rl HIGHEST /f

# Add hourly trigger
schtasks /create /tn $name /tr $script /sc hourly /mo 1 /st 00:00 /rl HIGHEST /f

# Enable "run if missed"
$xml = [xml](schtasks /query /tn $name /xml)
$ns = New-Object Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
$settings = $xml.SelectSingleNode("//t:Settings", $ns)
$settings.SelectSingleNode("//t:StartWhenAvailable", $ns).InnerText = "true"
$settings.SelectSingleNode("//t:DisallowStartIfOnBatteries", $ns).InnerText = "false"
$settings.SelectSingleNode("//t:StopIfGoingOnBatteries", $ns).InnerText = "false"
$tmp = "$env:TEMP\task_$name.xml"
$xml.Save($tmp)
schtasks /create /tn $name /xml $tmp /f

schtasks /query /tn $name
Write-Host "Done"
