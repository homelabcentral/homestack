# Roadmap

## 1. Pre-install steps

while deploying, if there are any pre-install steps in projects.json then ask user if they have completed the steps and only if the answer is yes for all then deploy the stack. eg. execute the deploy command.

## 2. Variable dependency

If the .env variables depend on some other variables that are present in the same file, it can use that value

## 3. Add DNS entry automatically to pihole

Add dns entry automatically to the local pihole instance using pihole python api, on failure warn user and let them know to add the entry manually.

## 4. Provide information rich message to users

Provide messages to user after deploying the stack such as what website to access the new container/service at.

## 5. Add a command to view secrets for a project

Add a new command to display secrets (only the ones user needs to save/remember with an option to show all) for a project

## 6. Add the password for a particular service to vaultwarden

Add the username, password automatically using python commands to the local vaultwarden

## 7. Add extends capabilities for .yml

Add common .yml files into `00.common` what can be extended into a `docker-compose.yml` file with questionary. for example, add nvidia block of code. Example already setup - immich. Control the flow using .env.template

## 8. Depends on a tag

## 9. Loading all env into memory (host.env, network.env)

## 10. Resolving variables from json, readme and env
