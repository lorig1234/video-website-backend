#!/bin/bash

# Script to convert 10-bit HEVC videos to 8-bit H.264 for browser compatibility
# This will make Attack on Titan videos play correctly in browsers

INPUT_DIR="/home/tony-server/website/video-website-split/video-website-backend/videos/Attack on titan"

echo "Converting 10-bit videos to browser-compatible 8-bit H.264..."
echo ""

find "$INPUT_DIR" -name "*.safari.mp4" -type f | while read -r file; do
    # Check if it's 10-bit
    pix_fmt=$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of default=noprint_wrappers=1:nokey=1 "$file")
    
    if [[ "$pix_fmt" == *"10"* ]]; then
        echo "Converting: $file"
        
        # Create backup filename
        backup="${file%.safari.mp4}.10bit.backup.mp4"
        output="${file%.safari.mp4}.temp.mp4"
        
        # Convert to 8-bit H.264 (most compatible)
        ffmpeg -i "$file" \
            -c:v libx264 \
            -preset medium \
            -crf 23 \
            -pix_fmt yuv420p \
            -c:a aac \
            -b:a 128k \
            -movflags +faststart \
            -y "$output" 2>/dev/null
        
        if [ $? -eq 0 ]; then
            # Rename original to backup and new file to original name
            mv "$file" "$backup"
            mv "$output" "$file"
            echo "✓ Converted successfully: $(basename "$file")"
        else
            echo "✗ Failed to convert: $(basename "$file")"
            rm -f "$output"
        fi
    else
        echo "Skipping (already 8-bit): $(basename "$file")"
    fi
done

echo ""
echo "Conversion complete!"
