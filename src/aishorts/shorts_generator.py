    async def _cleanup_assets(
        self,
        reel_series: ReelSeries | None,
        reel_outputs: list[ReelOutput],
        intermediate_keys: list[str],
        session_id: str,
        keep_assets: bool = False,
    ):
        if keep_assets:
            self.logger.info("Keep assets flag set. Skipping cleanup.")
            return

        self.logger.info("Cleaning up intermediate assets...")
        r2 = CloudflareR2()

        local_to_delete = set()
        r2_to_delete = set(intermediate_keys)

        # 1. Collect from reel_series blocks
        if reel_series:
            for reel in reel_series.reels:
                for block in reel.blocks:
                    assets = block.assets
                    if not assets:
                        continue

                    # Collect local files (only if they are in the 'output' directory)
                    for path in [
                        assets.voice_filepath,
                        assets.lipsync_filepath,
                        assets.staticface_filepath,
                        assets.question_filepath,
                        assets.song_filepath,
                    ]:
                        if path and os.path.exists(path) and "output" in path:
                            local_to_delete.add(path)

                    # Collect R2 keys
                    urls_to_check = [
                        assets.voice_url,
                        assets.lipsync_url,
                        assets.staticface_url,
                        assets.song_url,
                    ]
                    
                    for url in urls_to_check:
                        if url:
                            # Extract string if it's a dict
                            url_str = url.get("url") if isinstance(url, dict) else url
                            if url_str and str(url_str).startswith("http"):
                                try:
                                    key = CloudflareR2.get_key_from_url(url, r2.bucket)
                                    if key and not key.startswith("generated/"):
                                        r2_to_delete.add(key)
                                except:
                                    pass

                    # Media Map (Images, LaTeX, Manim)
                    for media_id, path in assets.media_map.items():
                        if path and os.path.exists(path) and "output" in path:
                            local_to_delete.add(path)
                        url = assets.media_url_map.get(media_id)
                        if url:
                            url_str = url.get("url") if isinstance(url, dict) else url
                            if url_str and str(url_str).startswith("http"):
                                try:
                                    key = CloudflareR2.get_key_from_url(url, r2.bucket)
                                    if key and not key.startswith("generated/"):
                                        r2_to_delete.add(key)
                                except:
                                    pass

        # 2. Protection: Do NOT delete final outputs (even if they were in the output dirs)
        final_local_paths = {ro.local_path for ro in reel_outputs}
        final_r2_keys = {
            CloudflareR2.get_key_from_url(ro.presigned_url, r2.bucket) for ro in reel_outputs
        }

        local_to_delete -= final_local_paths
        r2_to_delete -= final_r2_keys

        # 3. Delete local files
        for path in local_to_delete:
            try:
                os.remove(path)
                # self.logger.debug(f"Deleted local file: {path}")
            except Exception as e:
                self.logger.warning(f"Failed to delete local file {path}: {e}")

        # 4. Delete R2 objects
        for key in r2_to_delete:
            try:
                await asyncio.to_thread(r2.delete_file, key)
                # self.logger.debug(f"Deleted R2 object: {key}")
            except Exception as e:
                self.logger.warning(f"Failed to delete R2 key {key}: {e}")

        # 5. Finally, clean up the session uploads prefix (for on-the-fly uploads from providers)
        try:
            uploads_prefix = f"uploads/{session_id}/"
            await asyncio.to_thread(r2.delete_prefix, uploads_prefix)
        except Exception as e:
            self.logger.warning(f"Failed to clean up uploads prefix: {e}")
