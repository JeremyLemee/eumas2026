package interaction;

import ontologies.BDIOnt;
import ontologies.HMAS;
import cartago.Artifact;
import cartago.INTERNAL_OPERATION;
import cartago.OPERATION;
import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import jason.asSyntax.ASSyntax;
import jason.asSyntax.Atom;
import jason.asSyntax.Literal;
import jason.asSyntax.NumberTerm;
import jason.asSyntax.StringTerm;
import jason.asSyntax.Term;
import jason.NoValueException;
import org.eclipse.rdf4j.model.BNode;
import org.eclipse.rdf4j.model.IRI;
import org.eclipse.rdf4j.model.Model;
import org.eclipse.rdf4j.model.Resource;
import org.eclipse.rdf4j.model.Statement;
import org.eclipse.rdf4j.model.Value;
import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.LinkedHashModel;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;
import org.eclipse.rdf4j.model.util.Models;
import org.eclipse.rdf4j.model.vocabulary.RDF;
import org.eclipse.rdf4j.model.vocabulary.RDFS;
import org.eclipse.rdf4j.rio.RDFFormat;
import org.eclipse.rdf4j.rio.RDFParser;
import org.eclipse.rdf4j.rio.Rio;
import org.eclipse.rdf4j.rio.WriterConfig;
import org.eclipse.rdf4j.rio.helpers.BasicWriterSettings;
import org.eclipse.rdf4j.rio.helpers.StatementCollector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.StringWriter;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Hashtable;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * InteractionArtifact combines agent profiling, goal management, and semantic messaging.
 * Exposes a single HTTP server on port 8082 with endpoints for /profile, /ontologies, /message, and /annotations.
 */
public class InteractionArtifact extends Artifact {

    private HttpServer server;
    private Model agentProfile;
    private Map<String, Model> ontologies;
    private String profileDocumentUrl = "http://localhost:8082/profile";
    private String annotationServiceUrl;
    private String directMessageServiceUrl;
    private final ValueFactory rdf = SimpleValueFactory.getInstance();
    private static final Logger logger = LoggerFactory.getLogger(interaction.InteractionArtifact.class);
    private String ontologyNamespace = "http://example.org/lab#";
    private String bdiOntologyNamespace = "http://localhost:8082/ontologies/bdi#";

    private IRI lightIri;
    private IRI lightStateIri;
    private IRI hasLightStateIri;
    private IRI asturnIri;
    private IRI asProposeTurnIri;
    private IRI onStateIri;
    private IRI offStateIri;
    private IRI predicateAbilityIri;
    private IRI hasPredicateIri;
    private IRI hasValuesIri;
    private IRI setIri;
    private IRI setGoalIri;
    private IRI disableZ1BlindsGoalIri;
    private IRI disableZ2BlindsGoalIri;
    private IRI setL1OnGoalIri;
    private IRI setL1OffGoalIri;
    private IRI setL2OnGoalIri;
    private IRI setL2OffGoalIri;
    private IRI setB1OpenGoalIri;
    private IRI setB1CloseGoalIri;
    private IRI setB2OpenGoalIri;
    private IRI setB2CloseGoalIri;
    private IRI turnOnLightGoalIri;
    private IRI turnOffLightGoalIri;

    private final Set<String> perceivedAnnotationIds = new HashSet<>();
    private final Set<String> perceivedMessageIds = new HashSet<>();

    private static final int DEFAULT_HTTP_PORT = 8082;

    void init() throws IOException {
        configureOntologyNamespace(DEFAULT_HTTP_PORT);
        configureProfileDocumentUrl(DEFAULT_HTTP_PORT);
        initializeProfile();
        startHttpServer(DEFAULT_HTTP_PORT);
    }

    void init(int port) throws IOException {
        configureOntologyNamespace(port);
        configureProfileDocumentUrl(port);
        initializeProfile();
        startHttpServer(port);
    }

    @OPERATION
    public void sendHttpRequest(String method, String url, String headersJson, String payload) {
        Map<String, String> headers = new Hashtable<>();
        if (headersJson != null && !headersJson.isBlank()) {
            headers.putAll(new Gson().fromJson(headersJson, new TypeToken<Map<String, String>>() {}.getType()));
        }

        int code = sendRequestPayload(url, method, headers, payload == null ? "" : payload);
        if (code < 200 || code >= 300) {
            failed("http_request_failed");
        }
    }

    @OPERATION
    public void registerProfile(String thingDescriptionUrl, String profileUrl) {
        try {
            String tdJson = readHttpBody(thingDescriptionUrl, "application/td+json, application/json");
            com.google.gson.JsonObject td = com.google.gson.JsonParser.parseString(tdJson).getAsJsonObject();
            cacheAnnotationServiceUrl(td, thingDescriptionUrl);
            com.google.gson.JsonObject actions = td.getAsJsonObject("actions");
            if (actions == null) {
                throw new IOException("Thing Description does not expose actions");
            }

            AffordanceOperation target = null;
            for (Map.Entry<String, com.google.gson.JsonElement> entry : actions.entrySet()) {
                if (!entry.getValue().isJsonObject()) {
                    continue;
                }
                com.google.gson.JsonObject action = entry.getValue().getAsJsonObject();
                if (!hasAffordanceType(action, "hmas:registerProfile", "https://purl.org/hmas/registerProfile")) {
                    continue;
                }

                com.google.gson.JsonArray forms = action.getAsJsonArray("forms");
                if (forms == null || forms.isEmpty()) {
                    continue;
                }

                com.google.gson.JsonObject form = forms.get(0).getAsJsonObject();
                String href = getRequiredString(form, "href");
                String method = form.has("htv:methodName") ? form.get("htv:methodName").getAsString() : "POST";
                target = new AffordanceOperation(resolveHref(thingDescriptionUrl, href), method);
                break;
            }

            if (target == null) {
                throw new IOException("No registerProfile affordance found in Thing Description");
            }

            com.google.gson.JsonObject payload = new com.google.gson.JsonObject();
            payload.addProperty("name", "jason_profile");
            payload.addProperty("url", profileUrl);

            Map<String, String> headers = Map.of("Content-Type", "application/json");
            int status = sendRequestPayload(target.href, target.method, headers, payload.toString());
            if (status < 200 || status >= 300) {
                throw new IOException("Register profile request failed with status " + status);
            }
        } catch (Exception e) {
            logger.error("Failed to register profile {} from TD {}: {}", profileUrl, thingDescriptionUrl, e.getMessage());
            failed("register_profile_failed");
        }
    }

    @OPERATION
    public void setAbility(String abilityTypeUrl) {
        try {
            if (abilityTypeUrl == null || abilityTypeUrl.isBlank()) {
                failed("missing_ability_type");
                return;
            }

            ensureProfileInitialized();

            IRI agentIri = rdf.createIRI(profileDocumentUrl + "#agent");
            IRI abilityType = rdf.createIRI(abilityTypeUrl);

            if (hasAbility(agentIri, abilityType)) {
                logger.info("Ability {} already present in agent profile", abilityTypeUrl);
                return;
            }

            addAbility(agentIri, abilityType);

            logger.info("Added ability {} to agent profile", abilityTypeUrl);
        } catch (Exception e) {
            logger.error("Error in addAbility: {}", e.getMessage(), e);
            failed("add_ability_failed");
        }
    }

    @OPERATION
    public void setGoal(String goalUriString) {
        try {
            IRI goalUri = rdf.createIRI(goalUriString);
            IRI agentIri = rdf.createIRI(profileDocumentUrl + "#agent");

            java.util.Set<BNode> goalNodes = new java.util.HashSet<>();
            for (org.eclipse.rdf4j.model.Statement stmt : agentProfile.getStatements(agentIri, HMAS.hasGoal, null)) {
                if (stmt.getObject() instanceof BNode) {
                    goalNodes.add((BNode) stmt.getObject());
                }
            }

            for (BNode goalNode : goalNodes) {
                agentProfile.remove(goalNode, RDF.TYPE, null);
            }

            if (!goalNodes.isEmpty()) {
                BNode goalNode = goalNodes.iterator().next();
                agentProfile.add(goalNode, RDF.TYPE, goalUri);
            } else {
                BNode goalNode = rdf.createBNode();
                agentProfile.add(agentIri, HMAS.hasGoal, goalNode);
                agentProfile.add(goalNode, RDF.TYPE, goalUri);
            }

            logger.info("Agent goal updated to {}", goalUriString);

        } catch (Exception e) {
            logger.error("Error in setGoal: {}", e.getMessage(), e);
            failed("set_goal_failed");
        }
    }

    @OPERATION
    public void setAgentGoal(String goalUriString) {
        setGoal(goalUriString);
    }

    @OPERATION
    public void removeGoal(String goalUriString) {
        try {
            if (goalUriString == null || goalUriString.isBlank()) {
                failed("missing_goal_type");
                return;
            }

            ensureProfileInitialized();

            IRI agentIri = rdf.createIRI(profileDocumentUrl + "#agent");
            IRI goalUri = rdf.createIRI(goalUriString);
            Set<Resource> goalNodesToRemove = new HashSet<>();

            for (Statement stmt : agentProfile.getStatements(agentIri, HMAS.hasGoal, null)) {
                if (!(stmt.getObject() instanceof Resource goalNode)) {
                    continue;
                }

                if (agentProfile.contains(goalNode, RDF.TYPE, goalUri)) {
                    goalNodesToRemove.add(goalNode);
                }
            }

            for (Resource goalNode : goalNodesToRemove) {
                agentProfile.remove(agentIri, HMAS.hasGoal, goalNode);

                if (goalNode instanceof BNode bNode) {
                    removeGoalNodeSubgraph(bNode);
                } else {
                    agentProfile.remove(goalNode, null, null);
                }
            }

            logger.info("Removed {} goal node(s) with rdf:type {}", goalNodesToRemove.size(), goalUriString);
        } catch (Exception e) {
            logger.error("Error in removeGoal: {}", e.getMessage(), e);
            failed("remove_goal_failed");
        }
    }

    @OPERATION
    public void setAgentPredicateGoal(Term goalTerm) {
        try {
            if (goalTerm == null) {
                failed("missing_goal_term");
                return;
            }

            jason.asSyntax.Structure goalStructure = (jason.asSyntax.Structure) goalTerm;
            String predicate = goalStructure.getFunctor();

            if (predicate == null || predicate.isBlank()) {
                logger.error("Goal term has no predicate/functor: {}", goalTerm);
                failed("empty_goal_predicate");
                return;
            }

            IRI agentIri = rdf.createIRI(profileDocumentUrl + "#agent");
            removeExistingGoalDescriptions(agentIri);

            BNode goalNode = rdf.createBNode();
            agentProfile.add(agentIri, HMAS.hasGoal, goalNode);
            agentProfile.add(goalNode, RDF.TYPE, BDIOnt.set_goal);
            agentProfile.add(goalNode, BDIOnt.hasPredicate, rdf.createLiteral(predicate));

            BNode valuesList = createRdfListFromJasonTerms(goalStructure);
            agentProfile.add(goalNode, BDIOnt.hasValues, valuesList);

            logger.info("Agent predicate goal updated to {}", goalTerm);

        } catch (Exception e) {
            logger.error("Error in setAgentPredicateGoal: {}", e.getMessage(), e);
            failed("set_agent_predicate_goal_failed");
        }
    }

    @OPERATION
    public void setAgentPredicateGoalText(String goalText) {
        try {
            if (goalText == null || goalText.isBlank()) {
                failed("missing_goal_term");
                return;
            }

            Term parsedGoal = ASSyntax.parseTerm(goalText);

            if (!(parsedGoal instanceof jason.asSyntax.Structure)) {
                logger.error("Goal term is not a Jason structure: {}", parsedGoal);
                failed("goal_term_not_structure");
                return;
            }

            jason.asSyntax.Structure goalStructure = (jason.asSyntax.Structure) parsedGoal;
            String predicate = goalStructure.getFunctor();

            if (predicate == null || predicate.isBlank()) {
                logger.error("Goal term has no predicate/functor: {}", parsedGoal);
                failed("empty_goal_predicate");
                return;
            }

            IRI agentIri = rdf.createIRI(profileDocumentUrl + "#agent");
            removeExistingGoalDescriptions(agentIri);

            BNode goalNode = rdf.createBNode();
            agentProfile.add(agentIri, HMAS.hasGoal, goalNode);
            agentProfile.add(goalNode, RDF.TYPE, BDIOnt.set_goal);
            agentProfile.add(goalNode, BDIOnt.hasPredicate, rdf.createLiteral(predicate));

            BNode valuesList = createRdfListFromJasonTerms(goalStructure);
            agentProfile.add(goalNode, BDIOnt.hasValues, valuesList);

            logger.info("Agent predicate goal updated to {}", parsedGoal);

        } catch (Exception e) {
            logger.error("Error in setAgentPredicateGoalText: {}", e.getMessage(), e);
            failed("set_agent_predicate_goal_failed");
        }
    }

    @OPERATION
    public void queryAnnotations(String thingDescriptionUrl, String profileUrl) {
        try {
            String tdJson = readHttpBody(thingDescriptionUrl, "application/td+json, application/json");
            com.google.gson.JsonObject td = com.google.gson.JsonParser.parseString(tdJson).getAsJsonObject();
            cacheAnnotationServiceUrl(td, thingDescriptionUrl);
            com.google.gson.JsonObject actions = td.getAsJsonObject("actions");
            if (actions == null) {
                throw new IOException("Thing Description does not expose actions");
            }

            AffordanceOperation target = null;
            for (Map.Entry<String, com.google.gson.JsonElement> entry : actions.entrySet()) {
                if (!entry.getValue().isJsonObject()) {
                    continue;
                }
                com.google.gson.JsonObject action = entry.getValue().getAsJsonObject();
                if (!hasAffordanceType(action, "hmas:queryAnnotations", "https://purl.org/hmas/queryAnnotations")) {
                    continue;
                }

                com.google.gson.JsonArray forms = action.getAsJsonArray("forms");
                if (forms == null || forms.isEmpty()) {
                    continue;
                }

                com.google.gson.JsonObject form = forms.get(0).getAsJsonObject();
                String href = getRequiredString(form, "href");
                String method = form.has("htv:methodName") ? form.get("htv:methodName").getAsString() : "POST";
                target = new AffordanceOperation(resolveHref(thingDescriptionUrl, href), method);
                break;
            }

            if (target == null) {
                throw new IOException("No queryAnnotations affordance found in Thing Description");
            }

            String encodedProfile = java.net.URLEncoder.encode(profileUrl, StandardCharsets.UTF_8);
            String requestUrl = target.href.contains("?")
                    ? target.href + "&profile=" + encodedProfile
                    : target.href + "?profile=" + encodedProfile;

            HttpURLConnection connection = (HttpURLConnection) new URL(requestUrl).openConnection();
            connection.setRequestMethod(target.method);
            connection.setRequestProperty("Accept", "text/turtle, application/ld+json");

            int status = connection.getResponseCode();
            if (status == 404) {
                connection.disconnect();
                return;
            }
            if (status < 200 || status >= 300) {
                connection.disconnect();
                throw new IOException("Annotation query failed with status " + status);
            }

            String responseBody;
            String contentType = connection.getContentType();
            try (InputStream inputStream = connection.getInputStream()) {
                responseBody = readResponse(inputStream);
            } finally {
                connection.disconnect();
            }

            Model model = parseRdfString(responseBody, contentType == null ? "text/turtle" : contentType);
            materializeAnnotations(extractAnnotations(model));

        } catch (Exception e) {
            logger.error("Failed to query annotations: {}", e.getMessage());
            failed("query_annotations_failed");
        }
    }

    @OPERATION
    public void sendMessage(String receiverUrl, String belief) {
        System.out.println("send message to " + receiverUrl + " with belief: " + belief);
        Literal parsedBelief;
        try {
            parsedBelief = ASSyntax.parseLiteral(belief);
        } catch (Exception e) {
            failed("Could not parse belief '" + belief + "' as a Jason literal");
            return;
        }

        String senderUrl = profileDocumentUrl + "#agent";
        String targetUrl = directMessageServiceUrl;
        if (targetUrl == null || targetUrl.isBlank()) {
            failed("message_service_url_not_configured");
            return;
        }

        int code = sendMessagePayload(targetUrl, senderUrl, receiverUrl, parsedBelief);
        System.out.println("code: " + code);
        if (code < 200 || code >= 300) {
            failed("Message request failed with HTTP " + code);
        }
    }

    @OPERATION
    public void sendAnnotation(String belief) {
        System.out.println("send annotation with belief: " + belief);
        Literal parsedBelief;
        try {
            parsedBelief = ASSyntax.parseLiteral(belief);
        } catch (Exception e) {
            failed("Could not parse belief '" + belief + "' as a Jason literal");
            return;
        }

        String targetUrl = annotationServiceUrl;
        if (targetUrl == null || targetUrl.isBlank()) {
            failed("annotation_service_url_not_configured");
            return;
        }

        int code = sendAnnotationPayload(targetUrl, parsedBelief);
        System.out.println("code: " + code);
        if (code < 200 || code >= 300) {
            failed("Annotation request failed with HTTP " + code);
        }
    }

    private void startHttpServer(int port) throws IOException {
        server = HttpServer.create(new InetSocketAddress("localhost", port), 0);
        server.createContext("/profile", new ProfileHandler());
        server.createContext("/ontologies", new OntologyHandler());
        server.createContext("/message", new MessageHandler());
        server.createContext("/annotations", new AnnotationHandler());
        server.setExecutor(null);
        server.start();
        logger.info("InteractionArtifact HTTP server started on http://localhost:{}", port);
    }

    private class ProfileHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!exchange.getRequestMethod().equalsIgnoreCase("GET")) {
                exchange.sendResponseHeaders(405, 0);
                exchange.close();
                return;
            }

            try {
                writeRdfResponse(exchange, agentProfile);
            } catch (Exception e) {
                logger.error("Error in ProfileHandler: {}", e.getMessage());
                exchange.sendResponseHeaders(500, 0);
                exchange.close();
            }
        }
    }

    private class OntologyHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!exchange.getRequestMethod().equalsIgnoreCase("GET")) {
                exchange.sendResponseHeaders(405, 0);
                exchange.close();
                return;
            }

            String path = exchange.getRequestURI().getPath();
            String prefix = "/ontologies/";
            if (!path.startsWith(prefix) || path.length() <= prefix.length()) {
                exchange.sendResponseHeaders(404, 0);
                exchange.close();
                return;
            }

            String ontologyName = path.substring(prefix.length());
            Model ontology = ontologies.get(ontologyName);
            if (ontology == null) {
                exchange.sendResponseHeaders(404, 0);
                exchange.close();
                return;
            }

            try {
                writeRdfResponse(exchange, ontology);
            } catch (Exception e) {
                logger.error("Error in OntologyHandler: {}", e.getMessage());
                exchange.sendResponseHeaders(500, 0);
                exchange.close();
            }
        }
    }

    private class MessageHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!exchange.getRequestMethod().equalsIgnoreCase("POST")) {
                exchange.sendResponseHeaders(405, -1);
                exchange.close();
                return;
            }

            String body;
            try (InputStream requestBody = exchange.getRequestBody()) {
                body = readResponse(requestBody);
            }

            if (body == null || body.isBlank()) {
                exchange.sendResponseHeaders(400, -1);
                exchange.close();
                return;
            }

            String contentType = exchange.getRequestHeaders().getFirst("Content-Type");
            try {
                execInternalOp("applyReceivedMessage", body, contentType == null ? "" : contentType);
                exchange.sendResponseHeaders(202, -1);
            } catch (Exception e) {
                logger.error("Failed to process message payload", e);
                exchange.sendResponseHeaders(400, -1);
            } finally {
                exchange.close();
            }
        }
    }

    private class AnnotationHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!exchange.getRequestMethod().equalsIgnoreCase("POST")) {
                exchange.sendResponseHeaders(405, -1);
                exchange.close();
                return;
            }

            String body;
            try (InputStream requestBody = exchange.getRequestBody()) {
                body = readResponse(requestBody);
            }

            if (body == null || body.isBlank()) {
                exchange.sendResponseHeaders(400, -1);
                exchange.close();
                return;
            }

            String contentType = exchange.getRequestHeaders().getFirst("Content-Type");
            try {
                execInternalOp("applyReceivedAnnotations", body, contentType == null ? "" : contentType);
                exchange.sendResponseHeaders(202, -1);
            } catch (Exception e) {
                logger.error("Failed to process annotation payload", e);
                exchange.sendResponseHeaders(400, -1);
            } finally {
                exchange.close();
            }
        }
    }

    @INTERNAL_OPERATION
    void applyReceivedAnnotations(String body, String contentType) {
        Model model = parseRdfString(body, contentType);

        System.out.println("=== Received Annotations (Turtle) ===");
        System.out.println(formatCompactTurtle(model));
        System.out.println("=====================================");

        List<PerceivedAnnotation> annotations = extractAnnotations(model);
        materializeAnnotations(annotations);
    }

    @INTERNAL_OPERATION
    void applyReceivedMessage(String body, String contentType) {
        Model model = parseRdfString(body, contentType);

        System.out.println("=== Received Message (Turtle) ===");
        System.out.println(formatCompactTurtle(model));
        System.out.println("==================================");

        List<PerceivedMessage> messages = extractMessages(model);
        materializeMessages(messages);
    }

    private String formatCompactTurtle(Model model) {
        StringWriter writer = new StringWriter();
        WriterConfig config = new WriterConfig();
        config.set(BasicWriterSettings.PRETTY_PRINT, false);
        config.set(BasicWriterSettings.INLINE_BLANK_NODES, true);
        Rio.write(model, writer, RDFFormat.TURTLE, config);
        return writer.toString();
    }

    private List<PerceivedAnnotation> extractAnnotations(Model model) {
        List<PerceivedAnnotation> annotations = new ArrayList<>();
        for (Statement typeStatement : model.filter(null, RDF.TYPE, HMAS.Annotation)) {
            Resource annotationResource = typeStatement.getSubject();
            Resource contentId = findAnnotationContent(model, annotationResource);
            if (contentId == null) {
                continue;
            }

            String predicate = null;
            for (Statement predicateStatement : model.getStatements(contentId, BDIOnt.hasPredicate, null)) {
                if (predicateStatement.getObject() instanceof org.eclipse.rdf4j.model.Literal literal) {
                    predicate = literal.stringValue();
                    break;
                }
            }

            if (predicate == null || predicate.isBlank()) {
                continue;
            }

            List<Object> values = new ArrayList<>();
            for (Statement valueStatement : model.getStatements(contentId, BDIOnt.hasValues, null)) {
                if (valueStatement.getObject() instanceof Resource listHead) {
                    for (Value value : parseRDFList(model, listHead)) {
                        values.add(parseAnnotationValue(model, value));
                    }
                    break;
                }
            }

            annotations.add(new PerceivedAnnotation(
                findAnnotationId(model, annotationResource),
                annotationResource.stringValue(),
                predicate,
                values,
                serializeAnnotation(model, annotationResource)
            ));
        }
        return annotations;
    }

    private List<PerceivedMessage> extractMessages(Model model) {
        List<PerceivedMessage> messages = new ArrayList<>();
        for (Statement typeStatement : model.filter(null, RDF.TYPE, HMAS.Message)) {
            Resource messageId = typeStatement.getSubject();
            Resource contentId = findMessageContent(model, messageId);
            if (contentId == null) {
                continue;
            }

            String predicate = null;
            for (Statement predicateStatement : model.getStatements(contentId, BDIOnt.hasPredicate, null)) {
                if (predicateStatement.getObject() instanceof org.eclipse.rdf4j.model.Literal literal) {
                    predicate = literal.stringValue();
                    break;
                }
            }

            if (predicate == null || predicate.isBlank()) {
                continue;
            }

            List<Object> values = new ArrayList<>();
            for (Statement valueStatement : model.getStatements(contentId, BDIOnt.hasValues, null)) {
                if (valueStatement.getObject() instanceof Resource listHead) {
                    for (Value value : parseRDFList(model, listHead)) {
                        values.add(parseAnnotationValue(model, value));
                    }
                    break;
                }
            }

            String sender = findMessageSender(model, messageId);
            String receiver = findMessageReceiver(model, messageId);

            messages.add(new PerceivedMessage(findMessageId(model, messageId), predicate, values, sender, receiver));
        }
        return messages;
    }

    private void materializeAnnotations(List<PerceivedAnnotation> annotations) {
        for (PerceivedAnnotation annotation : annotations) {
            if (annotation.predicate().isBlank()) {
                continue;
            }

            String dedupKey = annotation.id() != null ? annotation.id() : annotation.uri();
            if (dedupKey != null && !perceivedAnnotationIds.add(dedupKey)) {
                continue;
            }

            logger.info(
                "Materializing annotation uri={} predicate={} values={} turtle=\n{}",
                annotation.uri(),
                annotation.predicate(),
                annotation.values(),
                annotation.turtle()
            );

            Object[] normalizedValues = annotation.values().stream()
                    .map(InteractionArtifact::normalizeAnnotationValue)
                    .toArray(Object[]::new);

            if (!hasObsProperty(annotation.predicate())) {
                defineObsProperty(annotation.predicate(), normalizedValues);
            } else {
                getObsProperty(annotation.predicate()).updateValues(normalizedValues);
            }

            Object[] debugValues = new Object[] {
                annotation.predicate(),
                annotation.uri(),
                annotation.id() == null ? "" : annotation.id(),
                annotation.turtle()
            };
            if (!hasObsProperty("annotation_debug")) {
                defineObsProperty("annotation_debug", debugValues);
            } else {
                getObsProperty("annotation_debug").updateValues(debugValues);
            }
        }
    }

    private void materializeMessages(List<PerceivedMessage> messages) {
        for (PerceivedMessage message : messages) {
            if (message.predicate().isBlank()) {
                continue;
            }

            if (message.id() != null && !perceivedMessageIds.add(message.id())) {
                continue;
            }

            logger.info("Materializing message predicate={} values={} from={} to={}",
                message.predicate(), message.values(), message.sender(), message.receiver());

            Object[] normalizedValues = message.values().stream()
                    .map(InteractionArtifact::normalizeAnnotationValue)
                    .toArray(Object[]::new);

            if (!hasObsProperty(message.predicate())) {
                defineObsProperty(message.predicate(), normalizedValues);
            } else {
                getObsProperty(message.predicate()).updateValues(normalizedValues);
            }
        }
    }

    private Resource findAnnotationContent(Model model, Resource annotationId) {
        for (Statement statement : model.getStatements(annotationId, HMAS.conveys, null)) {
            if (statement.getObject() instanceof Resource resource) {
                return resource;
            }
        }
        for (Statement statement : model.getStatements(annotationId, HMAS.signifies, null)) {
            if (statement.getObject() instanceof Resource resource) {
                return resource;
            }
        }
        return null;
    }

    private Resource findMessageContent(Model model, Resource messageId) {
        for (Statement statement : model.getStatements(messageId, HMAS.conveys, null)) {
            if (statement.getObject() instanceof Resource resource) {
                return resource;
            }
        }
        for (Statement statement : model.getStatements(messageId, HMAS.signifies, null)) {
            if (statement.getObject() instanceof Resource resource) {
                return resource;
            }
        }
        return null;
    }

    private String findAnnotationId(Model model, Resource annotationResource) {
        for (Statement statement : model.getStatements(annotationResource, HMAS.hasId, null)) {
            return statement.getObject().stringValue();
        }
        return null;
    }

    private String findMessageId(Model model, Resource messageResource) {
        for (Statement statement : model.getStatements(messageResource, HMAS.hasId, null)) {
            return statement.getObject().stringValue();
        }
        return null;
    }

    private String findMessageSender(Model model, Resource messageResource) {
        for (Statement statement : model.getStatements(messageResource, HMAS.hasSender, null)) {
            return statement.getObject().stringValue();
        }
        return null;
    }

    private String findMessageReceiver(Model model, Resource messageResource) {
        for (Statement statement : model.getStatements(messageResource, HMAS.hasReceiver, null)) {
            return statement.getObject().stringValue();
        }
        return null;
    }

    private String serializeAnnotation(Model model, Resource annotationResource) {
        Model annotationModel = new LinkedHashModel();
        Set<Resource> visited = new HashSet<>();
        copyAnnotationSubgraph(model, annotationResource, annotationModel, visited);

        StringWriter writer = new StringWriter();
        WriterConfig config = new WriterConfig();
        config.set(BasicWriterSettings.PRETTY_PRINT, true);
        config.set(BasicWriterSettings.INLINE_BLANK_NODES, true);
        Rio.write(annotationModel, writer, RDFFormat.TURTLE, config);
        return writer.toString();
    }

    private void copyAnnotationSubgraph(Model source, Resource subject, Model target, Set<Resource> visited) {
        if (!visited.add(subject)) {
            return;
        }

        for (Statement statement : source.getStatements(subject, null, null)) {
            target.add(statement);
            if (statement.getObject() instanceof Resource nestedResource) {
                copyAnnotationSubgraph(source, nestedResource, target, visited);
            }
        }
    }

    private Object parseAnnotationValue(Model model, Value value) {
        if (value instanceof org.eclipse.rdf4j.model.Literal literal) {
            return toJasonTermFromLiteral(literal.stringValue());
        }

        if (value instanceof Resource resource) {
            org.eclipse.rdf4j.model.Literal nestedPredicate = null;
            for (Statement statement : model.getStatements(resource, BDIOnt.hasPredicate, null)) {
                if (statement.getObject() instanceof org.eclipse.rdf4j.model.Literal literal) {
                    nestedPredicate = literal;
                    break;
                }
            }

            Resource nestedValuesHead = null;
            for (Statement statement : model.getStatements(resource, BDIOnt.hasValues, null)) {
                if (statement.getObject() instanceof Resource nestedResource) {
                    nestedValuesHead = nestedResource;
                    break;
                }
            }

            if (nestedPredicate != null && nestedValuesHead != null) {
                List<Value> nestedValues = parseRDFList(model, nestedValuesHead);
                Term[] args = new Term[nestedValues.size()];
                for (int i = 0; i < nestedValues.size(); i++) {
                    Value nestedValue = nestedValues.get(i);
                    if (nestedValue instanceof org.eclipse.rdf4j.model.Literal literal) {
                        args[i] = toJasonTermFromLiteral(literal.stringValue());
                    } else if (nestedValue instanceof Resource nestedResource) {
                        args[i] = toJasonTermFromResource(nestedResource);
                    } else {
                        args[i] = toJasonTermFromLiteral(nestedValue.stringValue());
                    }
                }
                return ASSyntax.createLiteral(nestedPredicate.stringValue(), args);
            }

            return toJasonTermFromResource(resource);
        }

        return value.stringValue();
    }

    private static Object normalizeAnnotationValue(Object value) {
        if (value == null) {
            return null;
        }

        if (value instanceof String stringValue) {
            try {
                return Integer.parseInt(stringValue);
            } catch (NumberFormatException ignored) {
            }
            try {
                return Long.parseLong(stringValue);
            } catch (NumberFormatException ignored) {
            }
            try {
                return Double.parseDouble(stringValue);
            } catch (NumberFormatException ignored) {
            }
            if ("true".equalsIgnoreCase(stringValue) || "false".equalsIgnoreCase(stringValue)) {
                return Boolean.parseBoolean(stringValue);
            }
            return stringValue;
        }

        if (value instanceof StringTerm stringTerm) {
            return stringTerm.getString();
        }

        return value;
    }

    private void removeExistingGoalDescriptions(IRI agentIri) {
        java.util.Set<BNode> goalNodes = new java.util.HashSet<>();

        for (org.eclipse.rdf4j.model.Statement stmt : agentProfile.getStatements(agentIri, HMAS.hasGoal, null)) {
            if (stmt.getObject() instanceof BNode) {
                goalNodes.add((BNode) stmt.getObject());
            }
        }

        agentProfile.remove(agentIri, HMAS.hasGoal, null);

        for (BNode goalNode : goalNodes) {
            removeGoalNodeSubgraph(goalNode);
        }
    }

    private void removeGoalNodeSubgraph(BNode goalNode) {
        java.util.Set<BNode> valueListNodes = new java.util.HashSet<>();

        for (org.eclipse.rdf4j.model.Statement stmt : agentProfile.getStatements(goalNode, BDIOnt.hasValues, null)) {
            if (stmt.getObject() instanceof BNode) {
                collectRdfListNodes((BNode) stmt.getObject(), valueListNodes);
            }
        }

        agentProfile.remove(goalNode, null, null);

        for (BNode listNode : valueListNodes) {
            agentProfile.remove(listNode, null, null);
        }
    }

    private void collectRdfListNodes(BNode listNode, java.util.Set<BNode> listNodes) {
        if (!listNodes.add(listNode)) {
            return;
        }

        for (org.eclipse.rdf4j.model.Statement stmt : agentProfile.getStatements(listNode, RDF.REST, null)) {
            if (stmt.getObject() instanceof BNode) {
                collectRdfListNodes((BNode) stmt.getObject(), listNodes);
            }
        }
    }

    private BNode createRdfListFromJasonTerms(jason.asSyntax.Structure structure) {
        BNode head = rdf.createBNode();
        BNode current = head;

        int arity = structure.getArity();

        if (arity == 0) {
            agentProfile.add(current, RDF.REST, RDF.NIL);
            return head;
        }

        for (int i = 0; i < arity; i++) {
            Term term = structure.getTerm(i);
            agentProfile.add(current, RDF.FIRST, rdf.createLiteral(jasonTermToLexicalValue(term)));

            if (i == arity - 1) {
                agentProfile.add(current, RDF.REST, RDF.NIL);
            } else {
                BNode next = rdf.createBNode();
                agentProfile.add(current, RDF.REST, next);
                current = next;
            }
        }

        return head;
    }

    private String jasonTermToLexicalValue(Term term) {
        if (term == null) {
            return "";
        }

        String value = term.toString();

        if (value.length() >= 2 && value.startsWith("\"") && value.endsWith("\"")) {
            return value.substring(1, value.length() - 1);
        }

        return value;
    }

    private void configureOntologyNamespace(int port) {
        bdiOntologyNamespace = "http://localhost:" + port + "/ontologies/bdi#";
        lightIri = rdf.createIRI(ontologyNamespace + "light");
        lightStateIri = rdf.createIRI(ontologyNamespace + "LightState");
        hasLightStateIri = rdf.createIRI(ontologyNamespace + "hasLightState");
        asturnIri = rdf.createIRI(ontologyNamespace + "ASTurn");
        asProposeTurnIri = rdf.createIRI(ontologyNamespace + "ASProposeTurn");
        onStateIri = rdf.createIRI(ontologyNamespace + "on");
        offStateIri = rdf.createIRI(ontologyNamespace + "off");
        predicateAbilityIri = BDIOnt.predicate_ability;
        hasPredicateIri = rdf.createIRI(bdiOntologyNamespace + "hasPredicate");
        hasValuesIri = rdf.createIRI(bdiOntologyNamespace + "hasValues");
        setIri = rdf.createIRI(bdiOntologyNamespace + "set");
        setGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_goal");
        disableZ1BlindsGoalIri = rdf.createIRI(bdiOntologyNamespace + "disable_z1_blinds");
        disableZ2BlindsGoalIri = rdf.createIRI(bdiOntologyNamespace + "disable_z2_blinds");
        setL1OnGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_l1_on");
        setL1OffGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_l1_off");
        setL2OnGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_l2_on");
        setL2OffGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_l2_off");
        setB1OpenGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_b1_open");
        setB1CloseGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_b1_close");
        setB2OpenGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_b2_open");
        setB2CloseGoalIri = rdf.createIRI(bdiOntologyNamespace + "set_b2_close");
    }

    private void configureProfileDocumentUrl(int port) {
        profileDocumentUrl = "http://localhost:" + port + "/profile";
    }

    private void initializeProfile() {
        agentProfile = new LinkedHashModel();
        IRI profileDocumentIRI = rdf.createIRI(profileDocumentUrl);
        IRI agentIRI = rdf.createIRI(profileDocumentUrl + "#agent");
        agentProfile.setNamespace("hmas", "https://purl.org/hmas/");
        agentProfile.setNamespace("lab", ontologyNamespace);
        agentProfile.setNamespace("bdi", bdiOntologyNamespace);
        agentProfile.add(profileDocumentIRI, HMAS.isProfileOf, agentIRI);
        agentProfile.add(agentIRI, RDF.TYPE, HMAS.Agent);

        addInteractionPolicies(agentIRI, buildServerUrl("annotations"), buildServerUrl("message"));

        initializeOntologies();
        logger.info("Initialized agent profile for {}", profileDocumentUrl);
    }

    private void addAbility(IRI agentIRI, IRI abilityType) {
        BNode ability = rdf.createBNode();
        agentProfile.add(agentIRI, HMAS.hasAbility, ability);
        agentProfile.add(ability, RDF.TYPE, abilityType);
    }

    private void ensureProfileInitialized() {
        if (agentProfile == null) {
            initializeProfile();
        }
    }

    private boolean hasAbility(IRI agentIRI, IRI abilityType) {
        for (Statement abilityLink : agentProfile.getStatements(agentIRI, HMAS.hasAbility, null)) {
            if (!(abilityLink.getObject() instanceof BNode abilityNode)) {
                continue;
            }

            if (agentProfile.contains(abilityNode, RDF.TYPE, abilityType)) {
                return true;
            }
        }
        return false;
    }

    private void addInteractionPolicies(IRI agentIRI, String callbackUrl, String messageUrl) {
        BNode policy = rdf.createBNode();
        agentProfile.add(agentIRI, HMAS.hasInteractionPolicy, policy);
        agentProfile.add(policy, RDF.TYPE, HMAS.RecurrentPolicy);
        agentProfile.add(policy, HMAS.hasCallbackUrl, rdf.createIRI(callbackUrl));
        BNode policy2 = rdf.createBNode();
        agentProfile.add(agentIRI, HMAS.hasInteractionPolicy, policy2);
        agentProfile.add(policy2, RDF.TYPE, HMAS.MessagePolicy);
        agentProfile.add(policy2, HMAS.hasMessageUrl, rdf.createIRI(messageUrl));
    }

    private void initializeOntologies() {
        ontologies = new HashMap<>();

        Model labOntology = new LinkedHashModel();
        labOntology.setNamespace("lab", ontologyNamespace);
        labOntology.setNamespace("rdf", RDF.NAMESPACE);
        labOntology.setNamespace("rdfs", RDFS.NAMESPACE);

        labOntology.add(lightIri, RDF.TYPE, RDFS.CLASS);
        labOntology.add(
                lightIri,
                RDFS.COMMENT,
                rdf.createLiteral("Belief predicate for light control commands.", "en")
        );

        labOntology.add(lightStateIri, RDF.TYPE, RDFS.CLASS);
        labOntology.add(
                lightStateIri,
                RDFS.COMMENT,
                rdf.createLiteral("State resource describing whether the light is currently on.", "en")
        );

        labOntology.add(hasLightStateIri, RDF.TYPE, RDF.PROPERTY);
        labOntology.add(
                hasLightStateIri,
                RDFS.COMMENT,
                rdf.createLiteral("Boolean property indicating whether the light is on.", "en")
        );

        labOntology.add(asturnIri, RDF.TYPE, RDFS.CLASS);
        labOntology.add(
                asturnIri,
                RDFS.COMMENT,
                rdf.createLiteral("Ability to process light control beliefs and trigger plans.", "en")
        );

        labOntology.add(asProposeTurnIri, RDF.TYPE, RDFS.CLASS);
        labOntology.add(
                asProposeTurnIri,
                RDFS.COMMENT,
                rdf.createLiteral("Ability to process Contract Net proposals for light control.", "en")
        );

        labOntology.add(onStateIri, RDF.TYPE, RDFS.RESOURCE);
        labOntology.add(
                onStateIri,
                RDFS.COMMENT,
                rdf.createLiteral("Symbol used in light(on) to request light be turned on.", "en")
        );

        labOntology.add(offStateIri, RDF.TYPE, RDFS.RESOURCE);
        labOntology.add(
                offStateIri,
                RDFS.COMMENT,
                rdf.createLiteral("Symbol used in light(off) to request light be turned off.", "en")
        );

        ontologies.put("lab", labOntology);
        ontologies.put("bdi", loadBdiOntology());
    }

    private Model loadBdiOntology() {
        Model bdiOntology = new LinkedHashModel();
        RDFParser rdfParser = Rio.createParser(RDFFormat.TURTLE);
        rdfParser.setRDFHandler(new StatementCollector(bdiOntology));

        try (InputStream inputStream = getClass().getClassLoader().getResourceAsStream("bdi.ttl")) {
            if (inputStream == null) {
                throw new IOException("Resource bdi.ttl not found in classpath");
            }
            rdfParser.parse(inputStream, "classpath:bdi.ttl");
        } catch (IOException e) {
            throw new IllegalStateException("Could not read BDI ontology from classpath", e);
        }

        return bdiOntology;
    }

    private void writeRdfResponse(HttpExchange exchange, Model model) throws IOException {
        RDFFormat format = getResponseFormat(exchange);
        String contentType = format.equals(RDFFormat.JSONLD) ? "application/ld+json" : "text/turtle";

        StringWriter writer = new StringWriter();
        WriterConfig config = new WriterConfig();
        config.set(BasicWriterSettings.PRETTY_PRINT, true);
        config.set(BasicWriterSettings.INLINE_BLANK_NODES, true);
        Rio.write(model, writer, format, config);

        byte[] responseBytes = writer.toString().getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.sendResponseHeaders(200, responseBytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(responseBytes);
        }
    }

    private RDFFormat getResponseFormat(HttpExchange exchange) {
        String acceptHeader = exchange.getRequestHeaders().getFirst("Accept");
        if (acceptHeader != null && acceptHeader.contains("application/ld+json")) {
            return RDFFormat.JSONLD;
        }
        return RDFFormat.TURTLE;
    }

    private int sendMessagePayload(String urlString, String senderUrl, String receiverUrl, Literal belief) {
        Model model = new LinkedHashModel();
        Resource messageId = rdf.createIRI(buildServerUrl("messages/" + generateId()));
        model.add(messageId, RDF.TYPE, HMAS.Message);
        model.add(messageId, HMAS.hasId, rdf.createLiteral(generateId()));
        model.add(messageId, HMAS.hasSender, rdf.createIRI(senderUrl));
        model.add(messageId, HMAS.hasReceiver, rdf.createIRI(receiverUrl));
        Resource ability = rdf.createBNode();
        model.add(messageId, HMAS.recommendsAbility, ability);
        model.add(ability, RDF.TYPE, BDIOnt.predicate_ability);
        model.add(messageId, HMAS.conveys, addBeliefResource(model, belief));

        StringWriter writer = new StringWriter();
        Rio.write(model, writer, RDFFormat.JSONLD);

        com.google.gson.JsonObject payload = new com.google.gson.JsonObject();
        payload.addProperty("agent", receiverUrl);
        payload.add("message", com.google.gson.JsonParser.parseString(writer.toString()));

        Map<String, String> headers = Map.of("Content-Type", "application/json");
        return sendRequestPayload(urlString, "POST", headers, payload.toString());
    }

    private int sendAnnotationPayload(String urlString, Literal belief) {
        Model model = new LinkedHashModel();
        Resource annotationId = rdf.createIRI(buildServerUrl("annotations/" + generateId()));
        model.add(annotationId, RDF.TYPE, HMAS.Annotation);
        model.add(annotationId, HMAS.hasId, rdf.createLiteral(generateId()));
        model.add(annotationId, HMAS.conveys, addBeliefResource(model, belief));

        Resource ability = rdf.createBNode();
        model.add(annotationId, HMAS.recommendsAbility, ability);
        model.add(ability, RDF.TYPE, BDIOnt.predicate_ability);
        model.add(annotationId, rdf.createIRI("http://example.org/lab#hasTimestamp"), rdf.createLiteral(Instant.now().toEpochMilli()));

        StringWriter writer = new StringWriter();
        Rio.write(model, writer, RDFFormat.JSONLD);

        Map<String, String> headers = Map.of("Content-Type", "application/ld+json");
        return sendRequestPayload(urlString, "POST", headers, writer.toString());
    }

    private Resource addBeliefResource(Model model, Literal belief) {
        Resource beliefId = rdf.createBNode();
        model.add(beliefId, BDIOnt.hasPredicate, rdf.createLiteral(belief.getFunctor()));
        model.add(beliefId, BDIOnt.hasValues, createRdfList(model, belief.getTerms()));
        return beliefId;
    }

    private Resource createRdfList(Model model, List<Term> terms) {
        if (terms == null || terms.isEmpty()) {
            return RDF.NIL;
        }

        Resource head = rdf.createBNode();
        Resource current = head;
        for (int i = 0; i < terms.size(); i++) {
            Term term = terms.get(i);
            model.add(current, RDF.FIRST, termToValue(model, term));
            Resource rest = (i == terms.size() - 1) ? RDF.NIL : rdf.createBNode();
            model.add(current, RDF.REST, rest);
            current = rest;
        }
        return head;
    }

    private Value termToValue(Model model, Term term) {
        if (term instanceof Literal nestedLiteral && nestedLiteral.getArity() > 0) {
            return addBeliefResource(model, nestedLiteral);
        }
        if (term instanceof StringTerm stringTerm) {
            return rdf.createLiteral(stringTerm.getString());
        }
        if (term instanceof NumberTerm numberTerm) {
            try {
                return rdf.createLiteral(numberTerm.solve());
            } catch (NoValueException e) {
                throw new IllegalArgumentException("Could not resolve numeric term: " + term, e);
            }
        }
        return rdf.createLiteral(term.toString());
    }

    private int sendRequestPayload(String urlString, String method, Map<String, String> headers, String payload) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(urlString).openConnection();
            connection.setRequestMethod(method);
            connection.setDoOutput(true);
            for (Map.Entry<String, String> entry : headers.entrySet()) {
                connection.setRequestProperty(entry.getKey(), entry.getValue());
            }

            byte[] body = payload.getBytes(StandardCharsets.UTF_8);
            if (body.length > 0) {
                try (OutputStream os = connection.getOutputStream()) {
                    os.write(body);
                }
            }

            return connection.getResponseCode();
        } catch (IOException e) {
            logger.error("Sending request with payload failed: {}", e.getMessage());
            return -1;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private String readHttpBody(String url, String acceptHeader) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod("GET");
        if (acceptHeader != null && !acceptHeader.isEmpty()) {
            connection.setRequestProperty("Accept", acceptHeader);
        }

        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) {
            throw new IOException("GET " + url + " failed with status " + status);
        }

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
            return body.toString();
        } finally {
            connection.disconnect();
        }
    }

    private static String readResponse(InputStream in) throws IOException {
        StringBuilder sb = new StringBuilder(4096);
        try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line).append('\n');
            }
        }
        return sb.toString();
    }

    private boolean hasAffordanceType(com.google.gson.JsonObject action, String compactType, String iriType) {
        com.google.gson.JsonElement typeElement = action.get("@type");
        if (typeElement == null) {
            return false;
        }
        if (typeElement.isJsonArray()) {
            for (com.google.gson.JsonElement item : typeElement.getAsJsonArray()) {
                if (item.isJsonPrimitive()) {
                    String value = item.getAsString();
                    if (compactType.equals(value) || iriType.equals(value)) {
                        return true;
                    }
                }
            }
            return false;
        }
        if (typeElement.isJsonPrimitive()) {
            String value = typeElement.getAsString();
            return compactType.equals(value) || iriType.equals(value);
        }
        return false;
    }

    private String getRequiredString(com.google.gson.JsonObject object, String key) throws IOException {
        com.google.gson.JsonElement value = object.get(key);
        if (value == null || !value.isJsonPrimitive()) {
            throw new IOException("Missing required TD field: " + key);
        }
        return value.getAsString();
    }

    private String resolveHref(String tdUrl, String href) {
        return java.net.URI.create(tdUrl).resolve(href).toString();
    }

    private String buildServerUrl(String path) {
        String baseUrl = profileDocumentUrl.replace("/profile", "");
        if (baseUrl.endsWith("/")) {
            return baseUrl + path;
        }
        return baseUrl + "/" + path;
    }

    private String generateId() {
        return UUID.randomUUID().toString();
    }

    public Model parseRdfString(String rdfString, String contentType) {
        String mimeType = contentType == null ? "" : contentType.split(";", 2)[0].trim();
        if ("application/json".equalsIgnoreCase(mimeType)) {
            mimeType = "application/ld+json";
        }
        RDFFormat format = Rio.getParserFormatForMIMEType(mimeType).orElse(RDFFormat.TURTLE);

        RDFParser rdfParser = Rio.createParser(format);
        Model model = new LinkedHashModel();
        rdfParser.setRDFHandler(new StatementCollector(model));

        try (InputStream inputStream = new ByteArrayInputStream(rdfString.getBytes(StandardCharsets.UTF_8))) {
            rdfParser.parse(inputStream, "http://localhost:8082/");
        } catch (Exception e) {
            logger.error("Error encountered when parsing RDF payload: {}", e.getMessage(), e);
        }

        return model;
    }

    private void cacheAnnotationServiceUrl(com.google.gson.JsonObject td, String thingDescriptionUrl) {
        String discoveredAnnotationUrl = findAnnotationServiceUrl(td, thingDescriptionUrl);
        if (discoveredAnnotationUrl != null && !discoveredAnnotationUrl.isBlank()) {
            annotationServiceUrl = discoveredAnnotationUrl;
        }

        String discoveredMessageUrl = findDirectMessageServiceUrl(td, thingDescriptionUrl);
        if (discoveredMessageUrl != null && !discoveredMessageUrl.isBlank()) {
            directMessageServiceUrl = discoveredMessageUrl;
        }
    }

    private String findAnnotationServiceUrl(com.google.gson.JsonObject td, String thingDescriptionUrl) {
        com.google.gson.JsonObject actions = td.getAsJsonObject("actions");
        if (actions != null) {
            for (Map.Entry<String, com.google.gson.JsonElement> entry : actions.entrySet()) {
                if (!entry.getValue().isJsonObject()) {
                    continue;
                }

                com.google.gson.JsonObject action = entry.getValue().getAsJsonObject();
                if (!hasAffordanceType(action, "hmas:queryAnnotations", "https://purl.org/hmas/queryAnnotations")) {
                    continue;
                }

                com.google.gson.JsonArray forms = action.getAsJsonArray("forms");
                if (forms == null || forms.isEmpty()) {
                    continue;
                }

                com.google.gson.JsonObject form = forms.get(0).getAsJsonObject();
                try {
                    return resolveHref(thingDescriptionUrl, getRequiredString(form, "href"));
                } catch (IOException ignored) {
                    // Fall through to other discovery strategies.
                }
            }
        }

        com.google.gson.JsonArray links = td.getAsJsonArray("links");
        if (links != null) {
            for (com.google.gson.JsonElement linkElement : links) {
                if (!linkElement.isJsonObject()) {
                    continue;
                }

                com.google.gson.JsonObject link = linkElement.getAsJsonObject();
                com.google.gson.JsonElement rel = link.get("rel");
                com.google.gson.JsonElement href = link.get("href");
                if (href == null || !href.isJsonPrimitive()) {
                    continue;
                }
                if (rel != null && rel.isJsonPrimitive() && "collection".equals(rel.getAsString())) {
                    return resolveHref(thingDescriptionUrl, href.getAsString());
                }
            }
        }

        return java.net.URI.create(thingDescriptionUrl).resolve("/annotations/").toString();
    }

    private String findDirectMessageServiceUrl(com.google.gson.JsonObject td, String thingDescriptionUrl) {
        com.google.gson.JsonObject actions = td.getAsJsonObject("actions");
        if (actions != null) {
            for (Map.Entry<String, com.google.gson.JsonElement> entry : actions.entrySet()) {
                if (!entry.getValue().isJsonObject()) {
                    continue;
                }

                com.google.gson.JsonObject action = entry.getValue().getAsJsonObject();
                if (!hasAffordanceType(action, "hmas:MessagePolicy", "https://purl.org/hmas/MessagePolicy")) {
                    continue;
                }

                com.google.gson.JsonArray forms = action.getAsJsonArray("forms");
                if (forms == null || forms.isEmpty()) {
                    continue;
                }

                com.google.gson.JsonObject form = forms.get(0).getAsJsonObject();
                try {
                    return resolveHref(thingDescriptionUrl, getRequiredString(form, "href"));
                } catch (IOException ignored) {
                    // Fall through to the default URL.
                }
            }
        }

        return java.net.URI.create(thingDescriptionUrl).resolve("/messages").toString();
    }

    public static List<Value> parseRDFList(Model model, Resource listIdentifier) {
        List<Value> items = new ArrayList<>();
        Resource current = listIdentifier;

        while (!current.equals(RDF.NIL)) {
            Models.object(model.filter(current, RDF.FIRST, null)).ifPresent(items::add);
            Value rest = Models.object(model.filter(current, RDF.REST, null)).orElse(null);
            if (rest instanceof Resource) {
                current = (Resource) rest;
            } else {
                break;
            }
        }
        return items;
    }

    private Term toJasonTermFromLiteral(String value) {
        if (value != null && value.matches("-?\\d+(?:\\.\\d+)?")) {
            return ASSyntax.createNumber(Double.parseDouble(value));
        }
        if (value != null && value.matches("[A-Za-z_][A-Za-z0-9_\\-.]*")) {
            return new Atom(value);
        }
        return ASSyntax.createString(value);
    }

    private Term toJasonTermFromResource(Resource res) {
        return new Atom(res.stringValue());
    }

    private record PerceivedAnnotation(String id, String uri, String predicate, List<Object> values, String turtle) {
    }

    private record PerceivedMessage(String id, String predicate, List<Object> values, String sender, String receiver) {
    }

    private static class AffordanceOperation {
        private final String href;
        private final String method;

        private AffordanceOperation(String href, String method) {
            this.href = href;
            this.method = method;
        }
    }
}
