class DFFG:
    def __init__(self, decay=0.9):
        self.decay = decay
        self.transitions = {i: {j: 0 for j in range(10)} for i in range(10)}
        self.intervals = {i: [] for i in range(10)}
        self.last_seen = {i: None for i in range(10)}
    
    def update(self, new_digit, tick):
        # Update interval memory
        for d in range(10):
            if self.last_seen[d] is not None:
                if d == new_digit:
                    interval = tick - self.last_seen[d]
                    self.intervals[d].append(interval)
        
        # Update transition weights with decay
        for a in range(10):
            for b in range(10):
                self.transitions[a][b] *= self.decay
        
        # Add recent transition weight
        if hasattr(self, "prev_digit"):
            self.transitions[self.prev_digit][new_digit] += 1
        
        self.prev_digit = new_digit
        self.last_seen[new_digit] = tick
    
    def predict_next(self):
        # Calculate transition probabilities
        next_probs = self.transitions[self.prev_digit]
        
        # Combine with interval expectations (frequency mod)
        modifier = {d: 1 for d in range(10)}
        for d, intervals in self.intervals.items():
            if intervals:
                avg_interval = sum(intervals[-min(len(intervals), 10):]) / min(len(intervals), 10)
                modifier[d] *= 1 / (1 + avg_interval)
        
        # Weighted probability fusion
        fused = {d: next_probs[d] * modifier[d] for d in range(10)}
        total = sum(fused.values())
        if total == 0:
            return None
        probs = {d: fused[d] / total for d in range(10)}
        
        # Return the most likely next digit
        return max(probs, key=probs.get)
