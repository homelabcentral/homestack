# How project works

Now, its time to make it all come together. This project is a tool, similar to homebrew which helps the user deploy the projects easily using docker compose. What projects are available for deployment are included in `projects.json`, this is the source of truth as to which projects are available to deploy. It has the information about project name, directory, it's `docker-compose.yml` file and `.env.template` file. with `homestack pull <project_name>` command it pulls down the docker compose.yml, .env.template and puts them into <project_name>/ directory inside the `INSTALL_DIR` from user preferences. `homestack deploy <project_name>` not only pulls the project but converts `.env.template` file into `.env` using questionary, write the file to disk and deploys the docker container.

All of these are cached locally and only synced if meta.json is different. User preferences are stored locally and fetched everytime the user runs a command and use any variables appropriately when needed. Tell me what is the best way to do this (to store the preferences). Keep in mind this tool will be installed via python and used from any command line/terminal from anywhere. It is crucial to store the user preferences described in the `homestack init` command below

It is a cli tool and the commands do as following:

1. `homestack help` or just `homestack`: it displays help for all the commands
2. `homestack init`: this command initializes user preferences. It fetches and stores these values - username, uid, gid, gid for docker group (if docker group does not exists then leave empty), processor architecture, processor logic count, total ram, and the storage of the disk of installation directory, and install directory (this is path type, use the same in questionary). get as many parameters as you can through python, ask for installation directory. Save these preferences. Recommend me how and where you plan to save these. and if init is already done show the user a message that is has already been setup. if it has not been initialized then run this command before the user tries to run any other command except `homestack` and `homestack help`
3. `homestack update`: fetches remote meta.json, env.json and projects.json, and caches them locally.
4. `homestack pull`: resolves projects urls from projects.json, downloads docker-compose.yml, .env.template and readme.md via Downloader (src/client/Downloader.py)

for the rest of the commands check (/workspaces/compose/00.homestack/src/cli/cli.py). Ask me any questions you might have. Use best practices. make sure it is robust. use production grade error handling, messages and logging. Use `uv` to manage packages. Add necessary commands to build the project in makefile.
