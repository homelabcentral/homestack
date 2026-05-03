# Questionary

I want to create a module for questionary that provides methods to ask questions of - text, password, file path, confirmation, select and form type. which is basically an abstraction for questionary library. Provide methods for each of these types of questions. Form type whose syntax is as below which takes in other different types of questions like text, password, file path, confirmation, and select. And provide a method that takes in the .env.template object and creates a form based questionary with differnt types of individual questions and returns a .env model. if the `--use-recommends` command is selected in the cli then the question is skipped and recommended value is used. If the recommended value is a password or passphrase or bcrypt hash then a new one is generated and at the end of the questionary it is displayed to the user with a note to the user to save it in a safe place.

Also create validators functions if applicable for each `type` for env.template value_type. for example, password(min, max) - password(8,20) should have the length between 8 and 20. same thing with passphrase. for port, it has to be between 1 to 65535, for `memory` value_type, it has to be XXK/M/G/T where XX is a number number, can be a single digit - for eg. 6M, 128G etc. float has to be float, int has to be int, ip has to be an ip address format. Dont validate the other value_type.

Ask me any question that you have.

```python
import questionary
from questionary import Choice
from pathlib import Path

answers = questionary.form(
    username=questionary.text(
        "Enter your username:",
        instruction="(letters and numbers only)",
        default="guest"
    ),

    password=questionary.password(
        "Enter your password:",
        instruction="(min 6 characters)"
    ),

    config_path=questionary.path(
        "Select config file path:",
        instruction="(must be an existing .json file)",
        default=str(Path.home() / "config.json"),
        only_files=True
    ),

    remember_me=questionary.confirm(
        "Remember login?",
        instruction="(stores credentials locally)",
        default=True
    ),

    role=questionary.select(
        "Select your role:",
        instruction="(use arrow keys)",
        choices=[
            Choice("User", value="user", description="Regular access with limited permissions"),
            Choice("Admin", value="admin", description="Full system control"),
            Choice("Guest", value="guest", description="Temporary minimal access"),
        ],
        default="User"
    )
).ask()

print(answers)
```
