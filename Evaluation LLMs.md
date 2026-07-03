# Evaluation of LLMs for Transformation Functions

We evaluate 3 transformations functions for the task of converting the annotation created by the CoALA agent into a representation that the BDI agent can process given its cognitive abilities. We call t1, the transformation function that uses predefined patterns to process the natural language goal. We call t2 the transformation function that uses LLM to process the natural language user goal present in the annotation. We call t3 the transformation function that
uses LLM in addition to generate of the content of the transformed annotation. For our evaluation, we use the following models through Ollama: gemma4:e2b, gemma4:e4b, gemma4:26b. In order to get more deterministic results, we set the temperature to 0 for each model, and we disable the use of reasoning in order to make the LLM more efficient to run. We evaluate the transformation functions on different goals.

## Goals

We present the goals on which the LLMs were evaluated. Each goal is characterized by: 1) a user goal in English (with a callback URL so that the BDI agent is able to reply to the CoALA agent), which is converted into an annotation, and 2) an AgentSpeak(L) belief, which should be written by the LLM and provided as content of the transformed annotation.

Goal 1.1 The user goal is: “Zone 1 should have light level 1. Zone 2 light level 2. Callback URL: http://localhost:8991/profile.” and the AgentSpeak(L) belief is: “set_env(1, 2, "http://localhost:8991/profile")”.

Goal 1.2 The user goal is: “1 should be the light level of zone 1. Zone 2 light level 2. Callback URL: http://localhost:8991/profile.” and the AgentSpeak(L) belief is: “set_env(1, 2, "http://localhost:8991/profile")”.

Goal 2.1 The user goal is: “Zone 1 should have light level 3. Zone 2 should have light level 2. A human will be in zone 1. Callback URL: http://localhost:8991/profile.” and the AgentSpeak(L) belief is: “set_env(3, 2, "http://localhost:8991/profile", human(1))”.

Goal 2.2 The user goal is: “Zone 1 should have light level 3. 2 is the light level of zone 2. In zone 1, there will be a human. The callback URL is http://localhost:8991/profile.” and the AgentSpeak(L) belief is: “set_env(3, 2, "http://localhost:8991/profile", human(1))”.

Goal 3.1 The user goal is: “Zone 1 should have light level 3. Zone 2 should have light level 1. A human will be in zone 1. A human will be in zone 2. Callback URL: http://localhost:8991/profile.” and the AgentSpeak(L) belief is: “set_env(3, 1, "http://localhost:8991/profile", human(1,2))”.

Goal 3.2 The user goal is: “1 is the light level of zone 2. Zone 1 should have light level 3. There will be a human in both zones. The profile URL is http://localhost:8991/profile.” and the AgentSpeak(L) belief is: “set_env(3, 1, "http://localhost:8991/profile", human(1,2))”.

## Results
We observe that t1 can properly transform the goal 1.1, 2.1, and 3.1. The goals 1.2, 2.2, and 3.2 should result in the same beliefs as 1.1, 2.1, and 3.1 respectively but they cannot be processed by our transformation function t1.
Therefore, t1 successfully transform the goals that follow the pattern (1.1, 2.1, and 3.1) but does not transform the goals that do not follow the pattern (1.2, 2.2, 3.2). We present our results in Table 1 for 30 iterations for each goal + LLM + transformation function, and we further detail the results depending on whether the goals follow the pattern or not in Table 2.

## Table 1: Results of different transformation functions on the goals with different LLMs

| Goal | Transformation Function | LLM | Success Rates (%) | Average Time (s)|
|:---:|:---:|:---:|:---:|:---:|
|Goal 1.1 | t2 | gemma4:e2b | 100 | 1.5 |
|Goal 1.1 | t2 | gemma4:e4b | 100 | 2.1 |
|Goal 1.1 | t2 | gemma4:e26b | 100 | 9.3 |
|Goal 1.2 | t2 | gemma4:e2b | 100 | 1.5 |
|Goal 1.2 | t2 | gemma4:e4b | 100 | 2 |
|Goal 1.2 | t2 | gemma4:e26b | 100 | 9.2 |
|Goal 2.1 | t2 | gemma4:e2b | 100 | 1.5 |
|Goal 2.1 | t2 | gemma4:e4b | 100 | 2 |
|Goal 2.1 | t2 | gemma4:e26b | 100 | 8.9 |
|Goal 2.2 | t2 | gemma4:e2b | 0 | 1.5 |
|Goal 2.2 | t2 | gemm4:e4b | 100 | 2.1 |
|Goal 2.2 | t2 | gemma4:e26b | 100 | 9.6 |
|Goal 3.1 | t2 | gemma4:e2b | 100 | 1.5 |
|Goal 3.1 | t2 | gemma4:e4b | 100 | 2.1 |
|Goal 3.1 | t2 | gemma4:e26b | 100 | 9.6 |
|Goal 3.2 | t2 | gemma4:e2b | 100 | 1.7 |
|Goal 3.2 | t2 | gemma4:e4b | 0 | 2.1 |
|Goal 3.2 | t2 | gemma4:e26b | 0 | 9.5 |
|Goal 1.1 | t3 | gemma4:e2b | 100 | 0.8 |
|Goal 1.1 | t3 | gemma4:e4b | 0 | 1.4 |
|Goal 1.1 | t3 | gemma4:e26b | 100 | 2.7 |
|Goal 1.2 | t3 | gemma4:e2b | 100 | 0.7 |
|Goal 1.2 | t3 | gemma4:e4b | 0 | 1.5 |
|Goal 1.2 | t3 | gemma4:e26b | 100 | 2.5 |
|Goal 2.1 | t3 | gemma4:e2b | 100 | 0.7 |
|Goal 2.1 | t3 | gemma4:e4b | 0 | 1.5 |
|Goal 2.1 | t3 | gemma4:e26b | 3.33 | 2.9 |
|Goal 2.2 | t3 | gemma4:e2b | 100 | 0.8 |
|Goal 2.2 | t3 | gemm4:e4b | 0 | 1.6 |
|Goal 2.2 | t3 | gemma4:e26b | 0 | 3.1 |
|Goal 3.1 | t3 | gemma4:e2b | 0 | 0.8 |
|Goal 3.1 | t3 | gemma4:e4b | 0 | 2 |
|Goal 3.1 | t3 | gemma4:e26b | 100 | 3.5 |
|Goal 3.2 | t3 | gemma4:e2b | 0 | 0.8 |
|Goal 3.2 | t3 | gemma4:e4b | 0 | 1.8 |
|Goal 3.2 | t3 | gemma4:e26b | 100 | 3.5 |

## Table 2: Average success rates and time for different transformation functions on different LLMs whether the goal follows the known pattern or not

| Transformation Function | LLM | Follow Pattern | Success Rates | Average Time (s)|
|:---:|:---:|:---:|:---:|:---:|
| t2 | gemma2:e2b | yes | 100 | 1.5 |
| t2 | gemma2:e2b | no | 66.7 | 1.6 |
| t2 | gemma2:e4b | yes | 100 | 2 |
| t2 | gemma2:e4b | no | 66.7 | 2 |
| t2 | gemma2:e26b | yes | 100 | 9.2 |
| t2 | gemma2:e26b | no | 66.7 | 9.4 |
| t3 | gemma2:e2b | yes | 66.7 | 0.8 |
| t3 | gemma2:e2b | no | 66.7 | 0.8 |
| t3 | gemma2:e4b | yes | 0 | 1.6 |
| t3 | gemma2:e4b | no | 0 | 1.6 |
| t3 | gemma2:e26b | yes | 68 | 3 |
| t3 | gemma2:e26b | no | 66.7 | 3 |

