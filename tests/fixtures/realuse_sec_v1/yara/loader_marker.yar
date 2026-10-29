rule SyntheticLoaderMarkers {
    strings:
        $a = "WinHttpRequest" ascii nocase
        $b = "VirtualAlloc" ascii nocase
    condition:
        any of them
}
