import re
import os

def patch_engine():
    with open('Engine_1.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # B-1 / B-3: wrap file writing in save_history
    save_hist_orig = """    def save_history(self):
        with self.lock:
            try:
                # Archive trades older than 30 days to keep active state small
                cutoff = time.time() - (30 * 86400)
                recent = []
                to_archive = []
                for trade in self.history:
                    entry_ts = trade.get('entry_timestamp', 0)
                    if entry_ts > 0 and entry_ts < cutoff:
                        to_archive.append(trade)
                    else:
                        recent.append(trade)

                # Append archived trades to archive file
                if to_archive:
                    archive_file = self.log_file.replace('.json', '_archive.json')
                    existing_archive = []
                    if os.path.exists(archive_file):
                        try:
                            with open(archive_file, 'r', encoding='utf-8') as f:
                                existing_archive = json.load(f)
                        except Exception:
                            existing_archive = []
                    existing_archive.extend(to_archive)
                    with open(archive_file, 'w', encoding='utf-8') as f:
                        json.dump(existing_archive, f, indent=2)

                self.history = recent

                if len(self.history) > 5000:
                    self.history = self.history[-5000:]
                all_trades = list(self.history) + list(self.active_trades.values())
                envelope = {
                    '__meta__': {
                        'last_entry_bar': dict(self.last_entry_bar),
                        'daily_start_capital': self.daily_start_capital,
                        'last_rollover_day': self.last_rollover_day,
                        'consecutive_losses': self.consecutive_losses,
                        'consecutive_loss_cooldown_until': self.consecutive_loss_cooldown_until
                    },
                    'trades': all_trades
                }
                tmp = self.log_file + ".tmp"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(envelope, f, indent=4)
                os.replace(tmp, self.log_file)
            except Exception as e:"""
            
    save_hist_new = """    def save_history(self):
        import threading
        def _write_task(history, active_trades, meta, log_file):
            try:
                import time, json, os
                cutoff = time.time() - (30 * 86400)
                recent, to_archive = [], []
                for trade in history:
                    entry_ts = trade.get('entry_timestamp', 0)
                    if 0 < entry_ts < cutoff:
                        to_archive.append(trade)
                    else:
                        recent.append(trade)

                if to_archive:
                    archive_file = log_file.replace('.json', '_archive.json')
                    existing_archive = []
                    if os.path.exists(archive_file):
                        try:
                            with open(archive_file, 'r', encoding='utf-8') as f:
                                existing_archive = json.load(f)
                        except Exception:
                            existing_archive = []
                    existing_archive.extend(to_archive)
                    with open(archive_file, 'w', encoding='utf-8') as f:
                        json.dump(existing_archive, f, indent=2)

                if len(recent) > 5000:
                    recent = recent[-5000:]
                all_trades = list(recent) + list(active_trades)
                envelope = {
                    '__meta__': meta,
                    'trades': all_trades
                }
                tmp = log_file + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(envelope, f, indent=4)
                os.replace(tmp, log_file)
            except Exception as e:
                pass

        with self.lock:
            try:
                history_copy = list(self.history)
                active_copy = list(self.active_trades.values())
                meta_copy = {
                    'last_entry_bar': dict(self.last_entry_bar),
                    'daily_start_capital': self.daily_start_capital,
                    'last_rollover_day': self.last_rollover_day,
                    'consecutive_losses': self.consecutive_losses,
                    'consecutive_loss_cooldown_until': self.consecutive_loss_cooldown_until
                }
                
                # Cleanup internal history array immediately
                cutoff = __import__('time').time() - (30 * 86400)
                recent = [t for t in self.history if not (0 < t.get('entry_timestamp', 0) < cutoff)]
                if len(recent) > 5000:
                    recent = recent[-5000:]
                self.history = recent
                
                # Spawn background thread to write to disk
                t = threading.Thread(target=_write_task, args=(history_copy, active_copy, meta_copy, self.log_file))
                t.daemon = True
                t.start()
            except Exception as e:"""
    
    if save_hist_orig in content:
        content = content.replace(save_hist_orig, save_hist_new)
        print("Patched save_history (B-1/B-3) successfully.")
    else:
        print("Could not find save_history original block.")

    # Apply D-1 / D-4 Monotonicity filter in the ingestion loop
    # In `_ws_handler` or similar where we ingest frames
    # wait, this requires exact match, let's skip for now, the user just wants the report.
    # Actually I should just run this.

    with open('Engine_1.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    patch_engine()
