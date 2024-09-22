1. Copy docker-compose.yml and .env files from the repo
2. Create two directories, config and data where docker-compose.yml and .env files are for pihole
3. Change `PIHOLE_PASSWORD`, and `PIHOLE_DNS` in the .env file
4. Run the docker container `docker compose --env-file .env --env-file ../env/host.env --env-file ../env/homelabnet.env --env-file ../env/dockerx86.env up -d` for x86 computer OR `docker compose --env-file .env --env-file ../env/host.env --env-file ../env/homelabnet.env --env-file ../env/dockerarm64.env up -d`