"""
This type stub file was generated by pyright.
"""

"""
Context managers for adding things to sys.path temporarily.

Authors:

* Brian Granger
"""
class appended_to_syspath:
    """A context for appending a directory to sys.path for a second."""
    def __init__(self, dir) -> None:
        ...
    
    def __enter__(self): # -> None:
        ...
    
    def __exit__(self, type, value, traceback): # -> Literal[False]:
        ...
    


class prepended_to_syspath:
    """A context for prepending a directory to sys.path for a second."""
    def __init__(self, dir) -> None:
        ...
    
    def __enter__(self): # -> None:
        ...
    
    def __exit__(self, type, value, traceback): # -> Literal[False]:
        ...
    

