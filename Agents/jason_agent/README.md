# jason-agent 

This project is for a Jason agent, implemented as part of a JaCaMo project. The purpose of these agents is to monitor the blinds of the lab environment

The agent code is present [`here`](src/agt/lab_agent.asl).



The code of the artifact to interact with the Interaction Platform is present [`here`](src/env/interaction/InteractionArtifact.java).



## TO RUN

On Linux and macOS:

````
./gradlew run
````

On Windows:

````
.\gradlew.bat run
````


## Runtime dependency

The light control artifacts do not start the lab server themselves. They send HTTP requests to `/control` on a separate lab service, which defaults to `http://localhost:8081`.


