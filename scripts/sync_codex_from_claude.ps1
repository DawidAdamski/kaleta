Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ClaudeAgentsDir = Join-Path $ProjectRoot ".claude\agents"
$ClaudeProjectContext = Join-Path $ProjectRoot "CLAUDE.md"
$CodexProjectContext = Join-Path $ProjectRoot "AGENTS.md"
$CodexHome = Join-Path $env:USERPROFILE ".codex"
$CodexAgentsDir = Join-Path $CodexHome "agents"
$CodexConfigPath = Join-Path $CodexHome "config.toml"
$ConfigBackupPath = Join-Path $CodexHome "config.toml.bak-kaleta-sync"

$ManagedBlockStart = "# BEGIN KALETA CODEX AGENTS"
$ManagedBlockEnd = "# END KALETA CODEX AGENTS"
$WritableAgents = @(
    "deps-updater",
    "docs-writer",
    "migration-creator",
    "scenario-runner",
    "seed-updater",
    "test-runner",
    "view-scaffolder"
)

function Get-ClaudeAgentMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $Content = Get-Content -Raw -LiteralPath $Path
    $FrontmatterMatch = [regex]::Match($Content, "(?s)\A---\s*(.*?)\s*---")
    if (-not $FrontmatterMatch.Success) {
        throw "Missing YAML frontmatter in $Path"
    }

    $Frontmatter = $FrontmatterMatch.Groups[1].Value
    $Metadata = @{}

    foreach ($Line in ($Frontmatter -split "`r?`n")) {
        if ($Line -match "^\s*([^:#]+?)\s*:\s*(.*?)\s*$") {
            $Metadata[$Matches[1]] = $Matches[2]
        }
    }

    if (-not $Metadata.ContainsKey("name")) {
        throw "Missing 'name' field in $Path"
    }

    if (-not $Metadata.ContainsKey("description")) {
        throw "Missing 'description' field in $Path"
    }

    if (-not $Metadata.ContainsKey("tools")) {
        $Metadata["tools"] = ""
    }

    return [PSCustomObject]@{
        Name = $Metadata["name"]
        Description = $Metadata["description"]
        Tools = $Metadata["tools"]
        SourcePath = (Resolve-Path -LiteralPath $Path).Path
    }
}

function Format-TomlString {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    return '"' + ($Value -replace '\\', '\\' -replace '"', '\"') + '"'
}

function Get-CodexSandboxMode {
    param(
        [Parameter(Mandatory = $true)]
        [string] $AgentName,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Tools
    )

    if ($WritableAgents -contains $AgentName) {
        return "workspace-write"
    }

    if ($Tools -match "\b(Write|Edit)\b") {
        return "workspace-write"
    }

    return "read-only"
}

function Sync-ProjectContextHardLink {
    if (-not (Test-Path -LiteralPath $ClaudeProjectContext)) {
        throw "Missing project context file: $ClaudeProjectContext"
    }

    if (-not (Test-Path -LiteralPath $CodexProjectContext)) {
        New-Item -ItemType HardLink -Path $CodexProjectContext -Target $ClaudeProjectContext | Out-Null
        Write-Host "Created AGENTS.md hardlink -> CLAUDE.md"
        return
    }

    $HardLinks = fsutil hardlink list $CodexProjectContext 2>$null
    if ($LASTEXITCODE -eq 0 -and ($HardLinks | Where-Object { $_ -like "*\CLAUDE.md" })) {
        Write-Host "AGENTS.md already hard-linked to CLAUDE.md"
        return
    }

    Write-Warning "AGENTS.md already exists but is not a hardlink to CLAUDE.md; leaving it untouched."
}

function Sync-CodexAgents {
    if (-not (Test-Path -LiteralPath $ClaudeAgentsDir)) {
        throw "Missing Claude agents directory: $ClaudeAgentsDir"
    }

    if (-not (Test-Path -LiteralPath $CodexAgentsDir)) {
        New-Item -ItemType Directory -Path $CodexAgentsDir | Out-Null
    }

    $Entries = @()
    $AgentFiles = Get-ChildItem -LiteralPath $ClaudeAgentsDir -Filter "*.md" | Sort-Object Name

    foreach ($AgentFile in $AgentFiles) {
        $Meta = Get-ClaudeAgentMetadata -Path $AgentFile.FullName
        $CodexAgentName = "kaleta-$($Meta.Name)"
        $SandboxMode = Get-CodexSandboxMode -AgentName $Meta.Name -Tools $Meta.Tools
        $TargetFileName = "$CodexAgentName.toml"
        $TargetPath = Join-Path $CodexAgentsDir $TargetFileName

        $Instructions = @"
You are the "$($Meta.Name)" specialist for the Kaleta project.

Before acting, open and follow this Claude source-of-truth file:
$($Meta.SourcePath)

Treat that file as the authoritative live prompt. If it changes, use the new version immediately instead of relying on stale memory.
"@

        $Toml = @"
model = "gpt-5.4"
model_reasoning_effort = "medium"
sandbox_mode = "$SandboxMode"
developer_instructions = '''
$Instructions
'''
"@

        Set-Content -LiteralPath $TargetPath -Value $Toml -NoNewline -Encoding utf8
        $Entries += [PSCustomObject]@{
            AgentName = $CodexAgentName
            Description = $Meta.Description
            ConfigFile = "agents/$TargetFileName"
            SandboxMode = $SandboxMode
            SourcePath = $Meta.SourcePath
        }
    }

    return $Entries
}

function Update-CodexConfig {
    param(
        [Parameter(Mandatory = $true)]
        [array] $Entries
    )

    if (-not (Test-Path -LiteralPath $CodexConfigPath)) {
        throw "Missing Codex config: $CodexConfigPath"
    }

    Copy-Item -LiteralPath $CodexConfigPath -Destination $ConfigBackupPath -Force

    $Config = Get-Content -Raw -LiteralPath $CodexConfigPath
    $BlockLines = @($ManagedBlockStart)

    foreach ($Entry in $Entries) {
        $BlockLines += ""
        $BlockLines += "[agents.$(Format-TomlString -Value $Entry.AgentName)]"
        $BlockLines += "description = $(Format-TomlString -Value $Entry.Description)"
        $BlockLines += "config_file = $(Format-TomlString -Value $Entry.ConfigFile)"
    }

    $BlockLines += ""
    $BlockLines += $ManagedBlockEnd
    $Block = [string]::Join("`n", $BlockLines)

    $Pattern = "(?s)$([regex]::Escape($ManagedBlockStart)).*?$([regex]::Escape($ManagedBlockEnd))"
    if ([regex]::IsMatch($Config, $Pattern)) {
        $UpdatedConfig = [regex]::Replace($Config, $Pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($Match) $Block }, 1)
    }
    else {
        $UpdatedConfig = $Config.TrimEnd() + "`n`n" + $Block + "`n"
    }

    Set-Content -LiteralPath $CodexConfigPath -Value $UpdatedConfig -NoNewline -Encoding utf8
}

Sync-ProjectContextHardLink
$Entries = Sync-CodexAgents
Update-CodexConfig -Entries $Entries

Write-Host ""
Write-Host "Synced $($Entries.Count) Kaleta agents into $CodexAgentsDir"
foreach ($Entry in $Entries) {
    Write-Host ("- {0} [{1}] <- {2}" -f $Entry.AgentName, $Entry.SandboxMode, $Entry.SourcePath)
}
Write-Host ""
Write-Host "Updated $CodexConfigPath"
Write-Host "Backup saved to $ConfigBackupPath"
