# 测试Windows位置 - 增强版
[Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null

Write-Host "Creating Geolocator..."
$locator = New-Object Windows.Devices.Geolocation.Geolocator
$locator.DesiredAccuracyInMeters = 10

Write-Host "Requesting position (may take 10-30 seconds)..."
$task = $locator.GetGeopositionAsync()

# 等待完成，最多30秒
$completed = $task.AsTask().Wait([TimeSpan]::FromSeconds(30))

if ($completed) {
    $position = $task.Result
    $coord = $position.Coordinate
    
    Write-Host "=== SUCCESS ==="
    Write-Host "Latitude: $($coord.Latitude)"
    Write-Host "Longitude: $($coord.Longitude)"
    Write-Host "Accuracy: $($coord.Accuracy) meters"
    
    # 检查是否有有效数据
    if ($coord.Latitude -ne 0 -and $coord.Longitude -ne 0) {
        $json = @{
            lat = [math]::Round($coord.Latitude, 6)
            lon = [math]::Round($coord.Longitude, 6)
            accuracy = [math]::Round($coord.Accuracy, 0)
            source = "Windows Location API (WinRT)"
            method = "Geolocator.GetGeopositionAsync"
        } | ConvertToJson -Compress
        
        Write-Host "JSON: $json"
        exit 0
    } else {
        Write-Host "ERROR: Coordinates are zero/null"
        Write-Host "Position timestamp: $($position.Coordinate.Timestamp)"
        exit 2
    }
} else {
    Write-Host "=== TIMEOUT ==="
    Write-Host "Location request timed out after 30 seconds"
    exit 1
}
