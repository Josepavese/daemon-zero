#!/bin/bash
# DaemonZero Docker Build & Push Helper

ORG="daemon0ai"
BASE_IMAGE="daemon-zero-base"
APP_IMAGE="daemon-zero"
TAG="latest"
BRANCH=${1:-"main"}

echo "=== DaemonZero Docker Build System (Branch: $BRANCH) ==="

# 1. Build Base Image
echo "[1/4] Building Base Image..."
docker build -t $ORG/$BASE_IMAGE:$TAG ./docker/base
docker tag $ORG/$BASE_IMAGE:$TAG $BASE_IMAGE:latest

# 2. Build App Image
echo "[2/4] Building App Image..."
docker build --build-arg BRANCH=$BRANCH -t $ORG/$APP_IMAGE:$TAG -f ./docker/run/Dockerfile ./docker/run

# 3. Local Tagging
docker tag $ORG/$APP_IMAGE:$TAG $APP_IMAGE:latest
docker tag $ORG/$APP_IMAGE:$TAG $APP_IMAGE:local

echo "[SUCCESS] Images built successfully."
echo "         - $ORG/$BASE_IMAGE:$TAG (also local $BASE_IMAGE:latest)"
echo "         - $ORG/$APP_IMAGE:$TAG (also local $APP_IMAGE:latest)"

# 4. Push to Registry (Optional)
read -p "Do you want to push to Docker Hub ($ORG)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo "[3/4] Pushing Base Image..."
    docker push $ORG/$BASE_IMAGE:$TAG
    echo "[4/4] Pushing App Image..."
    docker push $ORG/$APP_IMAGE:$TAG
    echo "[SUCCESS] Images pushed to registry."
fi
