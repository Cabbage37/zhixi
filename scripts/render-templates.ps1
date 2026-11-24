$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$word.Options.UpdateLinksAtOpen = $false
Write-Output "Word ready"
$items = @()
try {
 $i = 0
 foreach ($file in Get-ChildItem (Join-Path $root '文稿模板') -File | Sort-Object Name) {
  $i++
  $id = "template-$i"
  $pdf = [IO.Path]::GetFullPath((Join-Path $root "data/template-previews/$id.pdf"))
  $missing = [Type]::Missing
  Write-Output "Opening $id"
  $doc = $word.Documents.Open($file.FullName)
  Write-Output "Exporting $id"
  try { $doc.SaveAs2($pdf,17) } finally { $doc.Close(0) }
  $label = $file.BaseName -replace '^\d+\.',''
  if ($label.StartsWith('金控观察')) { $label = '金控观察' }
  $items += @{ id=$id; name=$label; file=$file.Name; preview="/templates/$id.png" }
 }
 $items | ConvertTo-Json | Set-Content (Join-Path $root 'web/templates/catalog.json') -Encoding utf8
} finally { $word.Quit() }
