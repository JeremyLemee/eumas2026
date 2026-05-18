# syntax=docker/dockerfile:1
FROM nodered/node-red:latest

# Put your flow into the container's userDir
COPY --chown=1000:1000 simulator_flow.json /data/flows.json
# (or keep your filename)
# ENV FLOWS=simulator_flow.json
# COPY --chown=1000:1000 simulator_flow.json /data/simulator_flow.json

EXPOSE 1880
# Use the base image's entrypoint/CMD unchanged
