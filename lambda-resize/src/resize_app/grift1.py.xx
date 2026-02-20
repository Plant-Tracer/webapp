        for packet in container.demux(vstream):
            for frame in packet.decode():
                if end_time is not None and frame.time is not None and frame.time > end_time:
                    break

                # → PIL image (RGB)
                img = frame.to_image()

                # Correct rotation first
                degrees = _rotation_degrees_from_frame(frame)
                img = _apply_rotation(img, degrees)

                # Decide target box per orientation (after rotation)
                w, h = img.size
                if w >= h:
                    # Landscape → fit inside 640x480
                    target_wh_this = (640, 480)
                else:
                    # Portrait → fit inside 480x640 (preserve portrait)
                    target_wh_this = (480, 640)

                # Downscale
                img = _resize_image(img, target_wh=target_wh_this, mode=mode)

                # JPEG → zip (no intermediates)
                bio = io.BytesIO()
                img.save(
                    bio,
                    format="JPEG",
                    quality=jpeg_quality,
                    optimize=True,
                    progressive=False,
                    subsampling=jpeg_subsampling,
                )
                bio.seek(0)
                zf.writestr(f"frame_{frame_index:06d}.jpg", bio.read())
                frame_index += 1
