rule SuspiciousScriptMarkers {
    meta:
        description = "Synthetic marker check for a defensive training fixture"
    strings:
        $a = "FromBase64String" ascii
        $b = "Invoke-Expression" ascii nocase
    condition:
        all of them
}
