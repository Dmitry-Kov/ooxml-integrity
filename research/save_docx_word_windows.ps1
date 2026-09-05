# Run in an ordinary, signed-in Windows desktop session with installed Word.
# Never pass seeded defects to Word: it may repair them during open/save.
[CmdletBinding()]
param(
    [string]$Batch,
    [switch]$Probe
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not [Environment]::UserInteractive) {
    throw 'Run this script in an interactive desktop user session, not a service.'
}
if (-not $Probe -and -not $Batch) { throw 'Specify -Batch or -Probe.' }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class EvidenceWordWindow {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
}
'@

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-BatchPath([string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative)) { throw 'Batch paths must be relative.' }
    $resolved = [IO.Path]::GetFullPath((Join-Path $script:batchRoot $Relative))
    if (-not $resolved.StartsWith($script:batchRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes the batch directory.' }
    return $resolved
}

$existingWord = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$word = $null
$documents = $null
$document = $null
$ownsWord = $false
$oldAutomationSecurity = $null
[object]$noSave = 0
try {
    if (-not $Probe) {
        $batchFile = (Resolve-Path -LiteralPath $Batch).Path
        $script:batchRoot = Split-Path -Parent $batchFile
        $request = Get-Content -Raw -LiteralPath $batchFile | ConvertFrom-Json
        if ($request.schema_version -ne 1 -or $request.operation -ne 'synthetic-clean-inputs-only') {
            throw 'Unsupported batch request.'
        }
        $logPath = Join-Path $script:batchRoot 'word-run.json'
        if (Test-Path -LiteralPath $logPath) { throw 'Use a fresh batch; run log already exists.' }
        foreach ($item in $request.documents) {
            $inputPath = Get-BatchPath $item.input
            $outputPath = Get-BatchPath $item.output
            if ([IO.Path]::GetExtension($inputPath) -ne '.docx' -or
                [IO.Path]::GetExtension($outputPath) -ne '.docx') { throw 'Only DOCX is accepted.' }
            if ((Get-Sha256 $inputPath) -ne $item.input_sha256) { throw 'Input hash mismatch.' }
            if (Test-Path -LiteralPath $outputPath) { throw 'Refusing to overwrite an output.' }
        }
    }

    # CreateObject, never GetActiveObject. Verify the process before modifying it.
    $word = New-Object -ComObject Word.Application
    $newWord = @(Get-Process WINWORD | Where-Object { $existingWord -notcontains $_.Id })
    if ($newWord.Count -ne 1) {
        throw 'Word did not create an isolated process; existing Word was left untouched.'
    }
    $wordProcess = $newWord[0].Id
    $documents = $word.Documents
    if ($documents.Count -ne 0) { throw 'New Word instance contains unexpected documents; left untouched.' }
    $ownsWord = $true
    $word.Visible = $false
    # Disable macros only in this instance and restore on exit. No Trust Center,
    # Protected View, registry, or global Office security settings are changed.
    $oldAutomationSecurity = $word.AutomationSecurity
    $word.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
    $word.DisplayAlerts = -1     # wdAlertsAll: never auto-accept a repair dialog

    $exe = Join-Path $word.Path 'WINWORD.EXE'
    $exeVersion = (Get-Item -LiteralPath $exe).VersionInfo.FileVersion
    $stream = [IO.File]::OpenRead($exe)
    $reader = New-Object IO.BinaryReader($stream)
    try {
        $stream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        $stream.Position = $peOffset + 4
        $machine = $reader.ReadUInt16()
    } finally { $reader.Dispose(); $stream.Dispose() }
    $architecture = switch ($machine) { 0x8664 { 'x64' } 0x014c { 'x86' } 0xaa64 { 'arm64' } default { throw 'Unknown Word architecture.' } }
    $windows = Get-CimInstance Win32_OperatingSystem
    $environment = [ordered]@{
        word_version = [string]$word.Version
        word_build = [string]$word.Build
        word_file_version = $exeVersion
        word_architecture = $architecture
        windows_caption = [string]$windows.Caption
        windows_version = [string]$windows.Version
        windows_build = [string]$windows.BuildNumber
        windows_architecture = [string]$windows.OSArchitecture
        powershell_version = $PSVersionTable.PSVersion.ToString()
    }
    if ($Probe) {
        $environment | ConvertTo-Json
    } else {
        $entries = @()
        foreach ($item in $request.documents) {
            [object]$inputPath = Get-BatchPath $item.input
            [object]$outputPath = Get-BatchPath $item.output
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $outputPath))
            Write-Output "Opening synthetic input $($item.id)"
            try {
                # ConfirmConversions=false, ReadOnly=true, AddToRecentFiles=false.
                # OpenAndRepair is omitted (default false); never request repair.
                # Keep the before bytes intact. Do not supply Missing placeholders:
                # some Office/PowerShell combinations reject them as type mismatches.
                # InvokeMember avoids PowerShell 5.1/Office ref-object coercion.
                $openArguments = [object[]]@([string]$inputPath, $false, $true, $false)
                $document = $documents.GetType().InvokeMember('Open',
                    [Reflection.BindingFlags]::InvokeMethod, $null, $documents, $openArguments)
                [uint32]$documentProcess = 0
                [void][EvidenceWordWindow]::GetWindowThreadProcessId(
                    [IntPtr]$document.Windows.Item(1).Hwnd, [ref]$documentProcess)
                if ($documentProcess -ne $wordProcess) { throw 'Document belongs to an unexpected Word process.' }
                $before = [ordered]@{
                    comments = $document.Comments.Count
                    tables = $document.Tables.Count
                    sections = $document.Sections.Count
                }
                # wdFormatXMLDocument=12, no recent-file entry or embedded fonts.
                $saveArguments = [object[]]@([string]$outputPath, 12, $false, '', $false,
                    '', $false, $false)
                [void]$document.GetType().InvokeMember('SaveAs2',
                    [Reflection.BindingFlags]::InvokeMethod, $null, $document, $saveArguments)
                if (-not $document.Saved) { throw 'Word did not report the document saved.' }
                $document.Close([ref]$noSave)
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
                $document = $null
                if ((Get-Sha256 $inputPath) -ne $item.input_sha256) { throw 'Word changed an input.' }
                $entries += [ordered]@{
                    id = $item.id
                    input = $item.input
                    input_sha256 = $item.input_sha256
                    output = $item.output
                    raw_output_sha256 = Get-Sha256 $outputPath
                    open_and_repair = $false
                    save_format = 12
                    saved = $true
                    input_object_counts = $before
                }
                $log = [ordered]@{
                    schema_version = 1
                    operation = 'Word.Application COM Documents.Open then Document.SaveAs2'
                    captured_at_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
                    environment = $environment
                    completed = ($entries.Count -eq $request.documents.Count)
                    documents = $entries
                }
                $log | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $logPath -Encoding UTF8
                Write-Output "Saved $($item.id)"
            } finally {
                if ($null -ne $document) {
                    $document.Close([ref]$noSave)
                    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
                    $document = $null
                }
            }
        }
    }
} finally {
    if ($ownsWord) {
        if ($null -ne $oldAutomationSecurity) { $word.AutomationSecurity = $oldAutomationSecurity }
        # Never close a document opened by somebody else during this run.
        if ($documents.Count -eq 0) { $word.Quit([ref]$noSave) }
        else { Write-Warning 'Unexpected open document; Word instance left running.' }
    }
    if ($null -ne $documents) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($documents) }
    if ($null -ne $word) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
