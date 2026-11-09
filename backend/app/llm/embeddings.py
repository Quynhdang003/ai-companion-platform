"""Fixed embedding size for every vector column (memories, KB chunks).

Changing it (or the embedding model) needs a migration and re-embedding everything
(architecture invariant 8).
"""

EMBEDDING_DIMS = 768
