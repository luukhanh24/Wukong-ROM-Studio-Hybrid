# Minimal posix symlink wrapper (restored stub for imgextractor.py)
import os


def symlink(source, link_name):
    """Create a symlink. On Windows, creates a file with the link target as content."""
    try:
        if os.name == 'nt':
            # Windows: try junction/symlink, fallback to writing target path
            try:
                os.symlink(source, link_name)
            except OSError:
                with open(link_name, 'w', encoding='utf-8') as f:
                    f.write(source)
        else:
            os.symlink(source, link_name)
    except Exception:
        pass


def readlink(path):
    """Read a symlink target, including the Windows fallback representation."""
    if os.path.islink(path):
        return os.readlink(path)
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return handle.read()
    except OSError:
        return None
