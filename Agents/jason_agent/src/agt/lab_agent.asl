profile_url("http://localhost:8082/profile").
lab_td_url("http://localhost:8081/td").
inp_td_url("http://localhost:5001/td").
sunshine_threshold(600).
disable_goal_uri(1, "http://localhost:8082/ontologies/bdi#disable_z1_blinds").
disable_goal_uri(2, "http://localhost:8082/ontologies/bdi#disable_z2_blinds").

!start.

+!start : inp_td_url(TD) & profile_url(ProfileUrl) <-
    setAbility("http://localhost:8082/ontologies/bdi#predicate_ability");
    setAbility("http://localhost:8082/ontologies/bdi#set_env");
    .print("Registering profile ", ProfileUrl, " using TD ", TD);
    registerProfile(TD, ProfileUrl);
    .print("Querying annotations for profile ", ProfileUrl);
    //queryAnnotations(TD, ProfileUrl);
    //!env_state_external(1,2);
     //sendAnnotation(goal(state(1, 2), ProfileUrl));
     //sendMessage("http://localhost:8991/profile#agent", done(true));
     //!prepare_human_zone(1);
    .print("end start").


/*
 * Belief-addition to achievement-goal adapters.
 *
 * These plans are intentionally thin. A belief addition such as +set(l1, off)
 * is treated as a request signal, immediately converted into an achievement
 * goal !set(l1, off).
 *
 * The belief is removed after conversion so that the same request can be
 * added again later and still generate a new +set(...) event.
 */

+set(Device, Mode) <-
    .print("Converting belief addition set(", Device, ", ", Mode, ") into goal !set(", Device, ", ", Mode, ")");
    -set(Device, Mode);
    !set(Device, Mode).

+env_state(Z1, Z2) <-
    .print("Converting belief addition env_state(", Z1, ", ", Z2, ") into goal !env_state(", Z1, ", ", Z2, ")");
    -env_state(Z1, Z2);
    !env_state(Z1, Z2).

+disable_z1_blinds(Sunshine, Status) <-
    .print("Converting belief addition disable_z1_blinds(", Sunshine, ", ", Status, ") into goal !disable_z1_blinds(", Sunshine, ", ", Status, ")");
    -disable_z1_blinds(Sunshine, Status);
    !disable_z1_blinds(Sunshine, Status).

+disable_z1_blinds(Sunshine, Status, Action) <-
    .print("Converting belief addition disable_z1_blinds(", Sunshine, ", ", Status, ", ", Action, ") into goal !disable_z1_blinds(", Sunshine, ", ", Status, ", ", Action, ")");
    -disable_z1_blinds(Sunshine, Status, Action);
    !disable_z1_blinds(Sunshine, Status, Action).

+annotation_debug(Predicate, AnnotationUri, AnnotationId, Turtle) <-
    .print("Annotation debug for predicate ", Predicate, " uri=", AnnotationUri, " id=", AnnotationId);
    .print("Annotation turtle:\n", Turtle).

+disable_z2_blinds(Sunshine, Status) <-
    .print("Converting belief addition disable_z2_blinds(", Sunshine, ", ", Status, ") into goal !disable_z2_blinds(", Sunshine, ", ", Status, ")");
    -disable_z2_blinds(Sunshine, Status);
    !disable_z2_blinds(Sunshine, Status).

+disable_z2_blinds(Sunshine, Status, Action) <-
    .print("Converting belief addition disable_z2_blinds(", Sunshine, ", ", Status, ", ", Action, ") into goal !disable_z2_blinds(", Sunshine, ", ", Status, ", ", Action, ")");
    -disable_z2_blinds(Sunshine, Status, Action);
    !disable_z2_blinds(Sunshine, Status, Action).

+set_env(Z1, Z2) <-
    .print("Converting belief addition set_env(", Z1, ", ", Z2, ") into goal !set_env(", Z1, ", ", Z2, ")");
    -set_env(Z1, Z2);
    !set_env(Z1, Z2).

+set_env(Z1, Z2, human(H1)) <-
    .print("Converting belief addition set_env(", Z1, ", ", Z2, ", human(", H1, ")) into goal !set_env(", Z1, ", ", Z2, ", human(", H1, "))");
    -set_env(Z1, Z2, human(H1));
    !set_env(Z1, Z2, human(H1)).

+set_env(Z1, Z2, human(H1, H2)) <-
    .print("Converting belief addition set_env(", Z1, ", ", Z2, ", human(", H1, ", ", H2, ")) into goal !set_env(", Z1, ", ", Z2, ", human(", H1, ", ", H2, "))");
    -set_env(Z1, Z2, human(H1, H2));
    !set_env(Z1, Z2, human(H1, H2)).

+set_env(Z1, Z2, Url) <-
    .print("Converting belief addition set_env(", Z1, ", ", Z2, ", ", Url, ") into goal !set_env(", Z1, ", ", Z2, ", ", Url, ")");
    +callback_url(Url);
    -set_env(Z1, Z2, Url);
    !set_env(Z1, Z2, Url).

+set_env(Z1, Z2, Url, human(H1)) <-
    .print("Converting belief addition set_env(", Z1, ", ", Z2, ", ", Url, ", human(", H1, ")) into goal !set_env(", Z1, ", ", Z2, ", ", Url, ", human(", H1, "))");
    +callback_url(Url);
    -set_env(Z1, Z2, Url, human(H1));
    !set_env(Z1, Z2, Url, human(H1)).

+set_env(Z1, Z2, Url, human(H1, H2)) <-
    .print("Converting belief addition set_env(", Z1, ", ", Z2, ", ", Url, ", human(", H1, ", ", H2, ")) into goal !set_env(", Z1, ", ", Z2, ", ", Url, ", human(", H1, ", ", H2, "))");
    +callback_url(Url);
    -set_env(Z1, Z2, Url, human(H1, H2));
    !set_env(Z1, Z2, Url, human(H1, H2)).


+!set_env(Z1, Z2) <-
    !set_env_core(Z1, Z2).

+!set_env(Z1, Z2, human(H1)) <-
    !prepare_human_zone(H1);
    !set_env_core(Z1, Z2).

+!set_env(Z1, Z2, human(H1, H2)) <-
    !prepare_human_zone(H1);
    !prepare_human_zone(H2);
    !set_env_core(Z1, Z2).

+!set_env(Z1, Z2, Url) <-
    !set_env_core(Z1, Z2);
    !notify_set_env_done(Url).

+!set_env(Z1, Z2, Url, human(H1)) <-
    !prepare_human_zone(H1);
    !set_env_core(Z1, Z2);
    !notify_set_env_done(Url).

+!set_env(Z1, Z2, Url, human(H1, H2)) <-
    !prepare_human_zone(H1);
    !prepare_human_zone(H2);
    !set_env_core(Z1, Z2);
    !notify_set_env_done(Url).

+!set_env_core(Z1, Z2): profile_url(Url) <-
    sendAnnotation(goal(state(Z1, Z2),Url)).

+!notify_set_env_done(Url): done(true) <-
    .print("Sending set_env completion annotation to ", Url);
    -done(true);
    sendMessage(Url, done(true)).

 +!notify_set_env_done(Url): done(false) <-
     .print("Sending set_env failed completion annotation to ", Url);
     -done(false);
     sendMessage(Url, done(false)).

 +!notify_set_env_done(Url): not done(true) & not done(false) <-
    .wait(100);
    !notify_set_env_done(Url).

+!prepare_human_zone(1)
    : disable_z1_blinds(Sunshine, Status) <-
    !disable_z1_blinds(Sunshine, Status).

+!prepare_human_zone(1)
    : disable_z1_blinds(Sunshine, Status, Action) <-
    !disable_z1_blinds(Sunshine, Status, Action).

+!prepare_human_zone(2)
    : disable_z2_blinds(Sunshine, Status) <-
    !disable_z2_blinds(Sunshine, Status).

+!prepare_human_zone(2)
    : disable_z2_blinds(Sunshine, Status, Action) <-
    !disable_z2_blinds(Sunshine, Status, Action).

+!prepare_human_zone(1)
    : profile_url(ProfileUrl)
      & inp_td_url(TD)
      & disable_goal_uri(1, GoalUri)
      & not disable_z1_blinds(_, _)
      & not disable_z1_blinds(_, _, _) <-
    .print("Requesting disable blinds goal for human in zone ", 1);
    setAgentGoal(GoalUri);
    queryAnnotations(TD, ProfileUrl);
    .wait(200);
    !prepare_human_zone(1).

+!prepare_human_zone(2)
    : profile_url(ProfileUrl)
      & inp_td_url(TD)
      & disable_goal_uri(2, GoalUri)
      & not disable_z2_blinds(_, _)
      & not disable_z2_blinds(_, _, _) <-
    .print("Requesting disable blinds goal for human in zone ", 2);
    setAgentGoal(GoalUri);
    queryAnnotations(TD, ProfileUrl);
    .wait(200);
    !prepare_human_zone(2).

+!disable_z1_blinds(Sunshine, false) <-
    .print("blinds are already disabled at sunshine ", Sunshine);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z1_blinds").

+!disable_z1_blinds(Sunshine, true, http_action(Method, Url, Headers, Payload))
    : sunshine_threshold(Threshold) & Sunshine > Threshold <-
    .print("Disabling zone 1 blinds because sunshine ", Sunshine, " exceeds threshold ", Threshold);
    sendHttpRequest(Method, Url, Headers, Payload);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z1_blinds").

+!disable_z1_blinds(Sunshine, true, http_action(_, _, _, _))
    : sunshine_threshold(Threshold) & not (Sunshine > Threshold) <-
    .print("Skipping zone 1 blinds disable because sunshine ", Sunshine, " does not exceed threshold ", Threshold);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z1_blinds").

+!disable_z1_blinds(Sunshine, true) <-
    .print("Zone 1 blinds are enabled but cannot yet be disabled because the required operation precondition is not satisfied at sunshine ", Sunshine);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z1_blinds").

+!disable_z2_blinds(Sunshine, false) <-
    .print("Zone 2 blinds are already disabled at sunshine ", Sunshine);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z2_blinds").

+!disable_z2_blinds(Sunshine, true, http_action(Method, Url, Headers, Payload))
    : sunshine_threshold(Threshold) & Sunshine > Threshold <-
    .print("Disabling zone 2 blinds because sunshine ", Sunshine, " exceeds threshold ", Threshold);
    sendHttpRequest(Method, Url, Headers, Payload);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z2_blinds").

+!disable_z2_blinds(Sunshine, true, http_action(_, _, _, _))
    : sunshine_threshold(Threshold) & not (Sunshine > Threshold) <-
    .print("Skipping zone 2 blinds disable because sunshine ", Sunshine, " does not exceed threshold ", Threshold);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z2_blinds").

+!disable_z2_blinds(Sunshine, true) <-
    .print("Zone 2 blinds are enabled but cannot yet be disabled because the required operation precondition is not satisfied at sunshine ", Sunshine);
    removeGoal("http://localhost:8082/ontologies/bdi#disable_z2_blinds").


/*
 * Predicate/environment-state goal.
 *
 * First case: the HTTP action is already known, so perform it.
 */

+!env_state(Z1, Z2)
    : http_action(Z1, Z2, Method, Url, Headers, Payload) <-
    .print("HTTP action already known for env_state(", Z1, ", ", Z2, ")");
    sendHttpRequest(Method, Url, Headers, Payload).


/*
 * Second case: the HTTP action is not yet known.
 * Request a predicate-level goal annotation, query annotations again,
 * then retry the achievement goal.
 */

+!env_state(Z1, Z2)
    : profile_url(ProfileUrl)
      & inp_td_url(TD)
      & not http_action(Z1, Z2, _, _, _, _) <-
    .print("No HTTP action belief for env_state(", Z1, ", ", Z2, "); requesting predicate annotation");
    setAgentPredicateGoal(env_state(Z1, Z2));
    queryAnnotations(TD, ProfileUrl);
    .wait(200);
    !env_state(Z1, Z2).


-!env_state(Z1, Z2) <-
    .print("Failed to achieve env_state(", Z1, ", ", Z2, ")").

+!env_state_external(Z1, Z2): profile_url(Url) <-
    sendAnnotation(goal(state(Z1, Z2),Url)).

+done(X): callback_url(Url) <-
    .print("Done message received");
    sendMessage(Url, done(X)).

+done(X): not callback_url(Url) <-
    .print("Done message cannot be sent").

{ include("$jacamo/templates/common-cartago.asl") }
