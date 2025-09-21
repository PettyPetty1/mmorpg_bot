
# Placeholder encoder; integrate torchvision or TinyConv later
class VisualEncoder:
    def __init__(self, out_dim: int = 256):
        self.out_dim = out_dim
    def to(self, device: str): return self
    def __call__(self, image): return None
