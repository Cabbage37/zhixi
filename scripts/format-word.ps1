param([string]$Source,[string]$Template,[string]$Destination)
$ErrorActionPreference='Stop'
$word=New-Object -ComObject Word.Application
$word.Visible=$false
$word.DisplayAlerts=0
$word.AutomationSecurity=3
$word.Options.UpdateLinksAtOpen=$false
try {
    $reference=$word.Documents.Open($Template,$false,$true)
    $sourceDoc=$word.Documents.Open($Source,$false,$true)
    $original=$sourceDoc.Content.Text
    # Select representative single-paragraph styles; never import sample body text.
    $samples=@{}
    function RoleOf($paragraph) {
        $line=$paragraph.Range.Text.Trim()
        if ($line -match '^[一二三四五六七八九十]+、') { return 'heading' }
        if ($line -match '^（[一二三四五六七八九十]+）') { return 'subheading' }
        if ($line -match '^[0-9]{4}年.*日$') { return 'date' }
        if ($paragraph.Alignment -eq 1 -and $line.Length -lt 80) { return 'title' }
        return 'body'
    }
    foreach ($p in $reference.Paragraphs) {
        $line=$p.Range.Text.Trim()
        if (!$line -or $p.Range.Information(12)) {continue}
        $role=RoleOf $p
        if (!$samples.ContainsKey($role) -or ($role -eq 'body' -and $line.Length -gt $samples[$role].Range.Text.Trim().Length)) {$samples[$role]=$p}
    }
    foreach ($section in $sourceDoc.Sections) {
        foreach ($prop in 'PageWidth','PageHeight','TopMargin','BottomMargin','LeftMargin','RightMargin','HeaderDistance','FooterDistance') {
            $section.PageSetup.$prop=$reference.Sections.Item(1).PageSetup.$prop
        }
        foreach ($which in 'Headers','Footers') {
            foreach ($kind in 1,2,3) {
                $from=$reference.Sections.Item(1).$which.Item($kind)
                if ($from.Exists) {$section.$which.Item($kind).Range.FormattedText=$from.Range.FormattedText}
            }
        }
    }
    $first=$true
    foreach ($p in $sourceDoc.Paragraphs) {
        if (!$p.Range.Text.Trim() -or $p.Range.Information(12)) {continue}
        $role=RoleOf $p
        if ($first -and $samples.ContainsKey('title')) {$role='title'}
        $first=$false
        if (!$samples.ContainsKey($role)) {continue}
        $style=$samples[$role]
        $p.Range.ParagraphFormat=$style.Range.ParagraphFormat.Duplicate
        $p.Range.Font=$style.Range.Characters.Item(1).Font.Duplicate
    }
    if ($original -cne $sourceDoc.Content.Text) {throw '正文一致性校验失败'}
    if ([IO.Path]::GetExtension($Destination) -eq '.pdf') {$sourceDoc.ExportAsFixedFormat($Destination,17)}
    else {$sourceDoc.SaveAs2($Destination,16)}
} finally {
    if ($sourceDoc) {$sourceDoc.Close(0)}
    if ($reference) {$reference.Close(0)}
    $word.Quit()
}
