# Simulator for Smart Factory Lighting

## Overview
The simulator is programmed in [Node-Red](https://nodered.org/) environment. To run the environment, you need to install Node-Red (basically a nodeJS-based programming tool) and import the [simulator_flow.json](simulator_flow.json).

### Steps
1. Install Node-Red by following [this installation guide](https://nodered.org/docs/getting-started/local). 
2. Start Node-Red:

```
node-red
```
3. Open the Node-Red editor by visiting http://127.0.0.1:1880/ in your browser.
4. On the top-right drop-down menu, select `Import`, and upload [simulator_flow.json](simulator_flow.json) to import it.
5. Deploy the simulator flow by selecting `Deploy`.
6. The status endpoint is http://localhost:1880/was/rl/status, and you can also interact with the simulated environment. Example response:

```json
{
  "Z1Level": 396.3840986447821,
  "Z2Level": 473.1920493223911,
  "Z1Light": false,
  "Z2Light": true,
  "Z1Blinds": true,
  "Z2Blinds": false,
  "Sunshine": 640.1482750972317,
  "TotalEnergyCost": 15,
  "EnergyCost": 0,
  "Hour": 1.5000000000000002
}
```

7. To send and action to the environment, POST the action as json payload to http://localhost:1880/was/rl/action
For example, to switch on the Z1 Lights:

```json
{

  "Z1Light": true

}
```

The response will confirm your action and provide a cost:

```json
{

  "Z1Light": true,
  "cost": 100
}
```

The simulator increments the time (Hour) by 0.1h every second and computes the new state of the environment. To keep things simple (intially), the Sunshine value hovers around 600..650. If you want to play with this, look at lines 11..20 in the "Update environment" node.
