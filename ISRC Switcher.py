import sqlite3

def update_song_isrc(db_path, old_isrc, new_isrc):
    # Connect to your SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if the old ISRC exists
        cursor.execute("SELECT isrc FROM song_history WHERE isrc = ?", (old_isrc,))
        row = cursor.fetchone()
        
        if row:
            # Update the record with the new ISRC
            cursor.execute("""
                UPDATE song_history 
                SET isrc = ? 
                WHERE isrc = ?
            """, (new_isrc, old_isrc))
            
            conn.commit()
            print(f"Successfully updated ISRC from {old_isrc} to {new_isrc}.")
        else:
            print(f"No song found with ISRC: {old_isrc}")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

# Provide your database file name and the ISRC values
database_file = 'instance/spotifyshuffler.db'
old_val = 'DEXO22576343'
new_val = 'DEXO22576343'

update_song_isrc(database_file, old_val, new_val)