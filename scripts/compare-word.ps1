param([string]$Source,[string]$Destination)
$ErrorActionPreference='Stop'
$word=New-Object -ComObject Word.Application
$word.Visible=$false
$word.DisplayAlerts=0
$word.AutomationSecurity=3
$word.Options.UpdateLinksAtOpen=$false
try {
 $doc=$word.Documents.Open($Source)
 try { $doc.SaveAs2($Destination,17) } finally { $doc.Close(0) }
} finally { $word.Quit() }
