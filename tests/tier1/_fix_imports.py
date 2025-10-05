import sys
import os

files = [
    'test_candle_aggregator.py',
    'test_features_simple.py', 
    'test_tier1_complete.py',
    'setup_database.py'
]

old_import = "sys.path.insert(0, '.')"
new_import = """# Add project root to path (two levels up from tests/tier1/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))"""

for filename in files:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if old_import in content:
            # Add os import if not present
            if 'import os' not in content:
                content = content.replace('import sys\n', 'import sys\nimport os\n')
            
            # Replace the path insert
            content = content.replace(old_import, new_import)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✓ Fixed {filename}")
        else:
            print(f"- Skipped {filename} (already fixed or no old import)")
            
    except Exception as e:
        print(f"✗ Error fixing {filename}: {e}")

print("\nDone!")
