# How to

## env.template parsing

inline env parsing and questionary prompts

there are many types of prompts, we will use the following:

1. text (to get the text input such as username etc)
2. password (to get password)
3. file path (to get the path of the file or directory)
4. confirmation (to confirm something)
5. select (to give the user an option to select if there are choices present)

and use all of these options into a questionary form which returns a directory which needs to be cast back into a .env file

.env.template file inline syntax:

1. key = value
2. recommended = value | generator(https://app_name.host_name.domain) - this generate based on preferences saved for the user, variables need to be exact. Use generator in order to generate the value of this particular key based on saved preferences or value of other keys available in the same .env file. May be add the generator thing later.
3. type = string|password|bcrypthash|memory|string(length)|passphrase(length)|random(length)|float(min, max)|int(min,max)|ip (This will be used to validate the input)|port
4. prompt = what prompt to ask the user when entering this variable
5. instruction = some basic instruction
6. choices = [choice1 (description=lorem ipsum, default=true), choice2 (description=lorem)]
7. immutable = true|false
8. description = what does this variable does (this is not used for questionary prompt)

all this does it gives us a key = value, value will be one of choices or user input, type validates the input against a validator function. and then key = value is the .env file which can be written to the drive for a project.

example:

PIHOLE_PASSWORD=password123! \# type=password | prompt = Enter the pasword for pihole web dashboard | instruction=Save this password someplace safe. You will need it to log into pihole. | choices=[] | immutable = false | description = This is the password for pihole web dashboard, you must set it up

DOCKER_IMAGE=pihole/pihole:latest \# type=string | prompt = Select a docker image to deploy | instruction = Literally doesn't matter which image you select, they are all the same | choices=[pihole/pihole:latest (description = This image is hosted on docker hub), ghcr.io/pihole:latest (default=true, description = This image is hosted on github)] | immutable = false | description = This is the docker image that will be used to deploy the pihole container, all docker images with the same tag are the same they are just hosted on different platforms

```python
    answers = questionary.form(
        docker_image = questionary.confirm(message="Would you like the next question?", default=True),
        pihole_password = questionary.select(message="Select item", choices=["item1", "item2", "item3"])
    ).ask()
```

flow of data:

1. get the .env.template path for a project from projects.json
2. fetch the .env.template into memory
3. convert into the .env.template pydantic model
4. create questionary based on the .env.template pydantic model
5. create the .env model (which is just basically key=value) based on the answers. if `--use-recommends` flag is enabled then use the recommended value for all the options that can be.
6. write the .env file on disk

## docker compose handling

docker compose for a project remains largely unchanged. for now, we can just download the file as it and write to disk

flow of data:

1. get the docker-compose.yml for a project from projects.json
2. fetch the docker-compose.yml into memory
3. optional - do some parsing or processing
4. write the docker-compose.yml to disk

## cli

cli is called `homestack` and it works similarly to homebrew. this is the orchestrator.

commands:

1. `homestack init`: initializes the homestack, get the configs such as user name, cpu cores, ram, install location etc. Take input from user if you want. Use sqlitedict to save user preferences and variables such as host name, username, uid, gid and other things that might not be used by containers
2. `homestack update`: it checks the remote api and checks if there are any containers that need updating or there are any more added projects/containers and saves locally
3. `homestack list`: lists all the projects available in projects.json, checks the list locally and if not then remotely
4. `homestack pull <project_name>`: pulls the docker compose and .env for a project
5. `homestack info <project_name>`: display information about the project
6. `homestack deploy <project_name> --use-recommended`: deploys all, provides post step instructions. --use-recommended skips user input which includes generating passwords and passphrases
7. `homestack search <project_name>`: searches if the specific project is available to deploy
8. `homestack upgrade <project_name>`: updates docker image to latest

## api

api has everything to interact with the remote "endpoint" eg. to pull data from the *.json files.

1. class RemoteClient with base url
2. various methods to fetch different data. for, env.json, meta.json and projects.json
3. methods to fetch docker-compose.yml, .env.template and readme.md provided the name of the directory

## models

1. a model for .env.template (from remote)
2. a model for .env (local model)
3. the meta.json, env.json and projects.json models stay the same
