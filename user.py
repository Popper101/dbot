class User:
    def __init__(self,id:str, max_ticks=20, is_demo:bool = True):
        self.user_id = id
        self.max_ticks = max_ticks
        self.bot_running = False
        self.is_demo = is_demo
        self.change_account_type()
    def change_account_type(self, is_demo:bool = None):
        if is_demo is not None:
            self.is_demo = is_demo
        if self.is_demo:
            self.API_TOKEN = "6aRpjKXBIQc51GC"
        else:
            self.API_TOKEN = "tG1mz5HIRkWYvWw"
        return self.API_TOKEN
    

class Users:
    def __init__(self):
        self.users = {}
    def add_user(self, user_id):
        if user_id not in self.users:
            user = User(user_id)
            self.users[user_id] = user
            return user
        return self.users[user_id]