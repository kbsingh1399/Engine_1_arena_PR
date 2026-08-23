# take_screenshot.ps1
# Save directory
$WorkspaceDir = "c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"
$ImagePath = Join-Path $WorkspaceDir "screenshot_1.png"

# Delete existing screenshot if it exists
if (Test-Path $ImagePath) {
    Remove-Item $ImagePath -Force
}

# Give a tiny delay for system window focus
Start-Sleep -Milliseconds 200

try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $Screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $Bounds = $Screen.Bounds
    $Bitmap = New-Object System.Drawing.Bitmap $Bounds.Width, $Bounds.Height
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    
    # Capture screen
    $Graphics.CopyFromScreen($Bounds.Location, [System.Drawing.Point]::Empty, $Bounds.Size)
    
    # Save image
    $Bitmap.Save($ImagePath, [System.Drawing.Imaging.ImageFormat]::Png)
    
    $Graphics.Dispose()
    $Bitmap.Dispose()
    
    # Clean up the scheduled task after successful run
    Unregister-ScheduledTask -TaskName "ArenaScreenshotTask" -Confirm:$false
} catch {
    # Log any error to a text file for debugging
    $ErrPath = Join-Path $WorkspaceDir "screenshot_err.txt"
    $_ | Out-File $ErrPath -Append
}
