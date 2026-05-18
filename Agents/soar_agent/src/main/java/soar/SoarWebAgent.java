package soar;

import com.sun.net.httpserver.HttpServer;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.HttpResponse;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.http.message.BasicClassicHttpRequest;
import org.eclipse.rdf4j.model.IRI;
import org.eclipse.rdf4j.model.Literal;
import org.eclipse.rdf4j.model.Model;
import org.eclipse.rdf4j.model.Resource;
import org.eclipse.rdf4j.model.Statement;
import org.eclipse.rdf4j.model.Value;
import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.LinkedHashModel;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;
import org.eclipse.rdf4j.model.util.ModelBuilder;
import org.eclipse.rdf4j.model.vocabulary.RDF;
import org.eclipse.rdf4j.rio.RDFFormat;
import org.eclipse.rdf4j.rio.Rio;
import org.eclipse.rdf4j.rio.WriterConfig;
import org.eclipse.rdf4j.rio.helpers.BasicWriterSettings;
import org.jsoar.kernel.Production;
import org.jsoar.kernel.ProductionType;
import org.jsoar.kernel.SoarProperties;
import org.jsoar.kernel.epmem.DefaultEpisodicMemory;
import org.jsoar.kernel.epmem.EpisodicMemoryStatistics;
import org.jsoar.kernel.io.InputOutput;
import org.jsoar.kernel.io.commands.OutputCommandHandler;
import org.jsoar.kernel.io.commands.OutputCommandManager;
import org.jsoar.kernel.io.quick.DefaultQMemory;
import org.jsoar.kernel.io.quick.QMemory;
import org.jsoar.kernel.io.quick.SoarQMemoryAdapter;
import org.jsoar.kernel.memory.Wme;
import org.jsoar.kernel.smem.DefaultSemanticMemory;
import org.jsoar.kernel.smem.SemanticMemoryStatistics;
import org.jsoar.kernel.symbols.Identifier;
import org.jsoar.runtime.ThreadedAgent;
import org.jsoar.util.adaptables.Adaptables;
import org.json.JSONArray;
import org.json.JSONObject;
import soar.ontologies.HMAS;
import soar.ontologies.SoarOnt;
import soar.rhs.*;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse.BodyHandlers;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SoarWebAgent {

    private static final String DEFAULT_AGENT_SOURCE = "src/main/java/soar/agents/light_processing.soar";
    private static final String DEFAULT_AGENT_NAME = "agent";
    private static final int DEFAULT_WEB_SERVER_PORT = 8083;
    private static final String SETUP4_PROFILE_REGISTRATION_NAME = "soar_profile";

    private final String agentName;
    private final ThreadedAgent agent;
    private final ValueFactory rdf = SimpleValueFactory.getInstance();

    private boolean handlersRegistered;

    private Model agentProfile;
    private IRI agentProfileId;
    private IRI agentId;

    private final Object profileLock = new Object();

    private final Set<String> processedAnnotationIds = new HashSet<>();
    private final Object annotationLock = new Object();

    private final Object perceivedInputLock = new Object();
    private final Set<InputTriple> perceivedInputTriples = new LinkedHashSet<>();
    private final Set<String> publishedQMemoryPaths = new LinkedHashSet<>();

    private long perceivedInputEventId = 0L;

    private final QMemory inputMemory = DefaultQMemory.create();
    private final Object inputMemoryLock = inputMemory;
    private SoarQMemoryAdapter inputAdapter;

    private static final class InputTriple {
        final String attribute;
        final String value;

        InputTriple(String attribute, String value) {
            this.attribute = Objects.requireNonNull(attribute, "attribute must not be null");
            this.value = Objects.requireNonNull(value, "value must not be null");
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof InputTriple other)) {
                return false;
            }
            return Objects.equals(attribute, other.attribute)
                    && Objects.equals(value, other.value);
        }

        @Override
        public int hashCode() {
            return Objects.hash(attribute, value);
        }
    }

    public SoarWebAgent(String agentName) {
        this.agentName = Objects.requireNonNull(agentName, "agentName must not be null");
        this.agent = ThreadedAgent.create(agentName);
    }

    public void start(String path) {
        try {
            initializeProfile();

            /*
             * Register custom RHS functions before sourcing the Soar file.
             * This avoids loading productions that reference unknown RHS functions.
             */
            registerHandlers();

            loadSource(path);

            System.out.println("agent is running before initialize: " + this.agent.isRunning());


            /*
             * QMemory is the source of external/perceived input. SoarQMemoryAdapter
             * publishes it onto the agent's input-link during JSoar input phases.
             */
            this.inputAdapter = SoarQMemoryAdapter.attach(this.agent.getAgent(), this.inputMemory);

            /*this.agent.getAgent().getEvents().addListener(
                    org.jsoar.kernel.events.InputEvent.class,
                    event -> {
                        synchronized (inputMemory) {
                            System.out.println("[DEBUG InputEvent] fired; QMemory paths = "
                                    + inputMemory.getPaths());
                        }

                        final var io = this.agent.getAgent().getInputOutput();
                        System.out.println("[DEBUG InputEvent] input-link = " + io.getInputLink());
                    });

            this.agent.getAgent().getEvents().addListener(
                    org.jsoar.kernel.events.StartEvent.class,
                    event -> System.out.println("[DEBUG StartEvent] agent started; isRunning="
                            + this.agent.isRunning()));

            this.agent.getAgent().getEvents().addListener(
                    org.jsoar.kernel.events.StopEvent.class,
                    event -> {
                        System.out.println("[DEBUG StopEvent] agent stopped; isRunning="
                                + this.agent.isRunning());

                        try {
                            System.out.println("[DEBUG StopEvent] stopPhase="
                                    + this.agent.getStopPhase());
                            System.out.println("[DEBUG StopEvent] dCycle="
                                    + this.agent.getAgent().getProperties()
                                    .get(org.jsoar.kernel.SoarProperties.D_CYCLE_COUNT));
                        } catch (Exception e) {
                            System.err.println("[DEBUG StopEvent] failed to inspect stop state: "
                                    + e.getMessage());
                        }
                    });

            this.agent.getAgent().getEvents().addListener(
                    org.jsoar.kernel.events.InputEvent.class,
                    event -> {
                        synchronized (inputMemory) {
                            System.out.println("[DEBUG InputEvent] fired; QMemory paths="
                                    + inputMemory.getPaths());
                        }

                        final var io = this.agent.getAgent().getInputOutput();
                        System.out.println("[DEBUG InputEvent] input-link=" + io.getInputLink());
                    });*/

            this.agent.initialize();

            startWebServer(DEFAULT_WEB_SERVER_PORT);

            this.agent.runForever();

            System.out.println("agent is running after runForever: " + this.agent.isRunning());
        } catch (Exception e) {
            throw new IllegalStateException("Failed to start Soar agent from source: " + path, e);
        }
    }

    private void initializeProfile() {
        final IRI profileDocumentId = rdf.createIRI("http://localhost:" + DEFAULT_WEB_SERVER_PORT + "/profile");
        agentId = rdf.createIRI("http://localhost:" + DEFAULT_WEB_SERVER_PORT + "/profile#agent");
        agentProfileId = profileDocumentId;

        final Resource soarAbilityNode = rdf.createBNode();
        final Resource soarLightProcessingNode = rdf.createBNode();
        final Resource wmeTurnNode = rdf.createBNode();
        final Resource policyNode = rdf.createBNode();

        final Model profile = new LinkedHashModel();
        profile.add(profileDocumentId, HMAS.isProfileOf, agentId);
        profile.add(agentId, RDF.TYPE, HMAS.Agent);
        profile.add(agentId, HMAS.hasAbility, soarAbilityNode);
        profile.add(soarAbilityNode, RDF.TYPE, SoarOnt.soar_ability);

        profile.add(agentId, HMAS.hasAbility, soarLightProcessingNode);
        profile.add(soarLightProcessingNode, RDF.TYPE, SoarOnt.soar_light_processing);

        profile.add(agentId, HMAS.hasAbility, wmeTurnNode);
        profile.add(wmeTurnNode, RDF.TYPE, SoarOnt.WMETurn);

        profile.add(agentId, HMAS.hasInteractionPolicy, policyNode);
        profile.add(policyNode, RDF.TYPE, HMAS.RecurrentPolicy);
        profile.add(policyNode, HMAS.hasCallbackUrl,
                rdf.createIRI("http://localhost:" + DEFAULT_WEB_SERVER_PORT + "/annotations"));

        synchronized (profileLock) {
            agentProfile = profile;
        }
    }

    private void loadSource(String path) throws Exception {
        Objects.requireNonNull(path, "path must not be null");

        if (path.startsWith("http://") || path.startsWith("https://")) {
            System.out.println("load source from url");
            this.agent.getInterpreter().source(new URL(path));
            return;
        }

        System.out.println("load local source");
        this.agent.getInterpreter().source(new File(path));
    }

    private void registerHandlers() {
        if (this.handlersRegistered) {
            return;
        }

        this.agent.getAgent().getRhsFunctions().registerHandler(new PrintActionHandler());
        new CountAction().setAgent(this.agent.getAgent());
        this.agent.getAgent().getRhsFunctions().registerHandler(new DiscretizeLightLevel(this.agent.getAgent()));
        this.agent.getAgent().getRhsFunctions().registerHandler(new KgValue(this.agent.getAgent()));
        this.agent.getAgent().getRhsFunctions().registerHandler(new KgActionField(this.agent.getAgent()));
        new KgActionField(this.agent.getAgent());
        new PrintList().setAgent(this.agent.getAgent());
        new Wait().setAgent(this.agent.getAgent());
        new Stop().setAgent(this.agent.getAgent());
        new StorePm().setAgent(this.agent.getAgent());

        registerOutputHandlers();

        this.handlersRegistered = true;
    }

    private void registerOutputHandlers() {
        OutputCommandManager outputCommandManager = new OutputCommandManager(this.agent.getEvents());

        outputCommandManager.registerHandler("register-profile", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleRegisterProfile(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });

        outputCommandManager.registerHandler("query-annotations", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleQueryAnnotations(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });

        outputCommandManager.registerHandler("send-http-request", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleSendHttpRequest(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });

        outputCommandManager.registerHandler("set-goal", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleSetGoal(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });

        outputCommandManager.registerHandler("clear-goal", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleClearGoal(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });

        outputCommandManager.registerHandler("set-agent-goal", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleSetAgentGoal(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });

        outputCommandManager.registerHandler("send-message", new OutputCommandHandler() {
            @Override
            public void onCommandAdded(String commandName, Identifier command) {
                handleSendMessage(command);
            }

            @Override
            public void onCommandRemoved(String commandName, Identifier command) {
            }
        });
    }

    private void setPerceivedInputTriples(Set<InputTriple> triples) {
        final Set<InputTriple> cleaned = new LinkedHashSet<>();

        for (InputTriple triple : triples) {
            final String attribute = sanitizeQMemoryPath(triple.attribute);
            final String value = triple.value.trim();

            if (!attribute.isBlank() && !value.isBlank()) {
                cleaned.add(new InputTriple(attribute, value));
            }
        }

        if (cleaned.isEmpty()) {
            System.out.println("[PendingInput] No publishable triples after cleaning.");
            return;
        }

        final long nextEventId;

        synchronized (perceivedInputLock) {
            perceivedInputTriples.clear();
            perceivedInputTriples.addAll(cleaned);
            perceivedInputEventId++;
            nextEventId = perceivedInputEventId;
        }

        synchronized (inputMemory) {
            for (String oldPath : publishedQMemoryPaths) {
                inputMemory.remove(oldPath);
            }
            publishedQMemoryPaths.clear();

            for (InputTriple triple : cleaned) {
                final Optional<Long> integerValue = parseLong(triple.value);

                if (integerValue.isPresent()) {
                    inputMemory.setInteger(triple.attribute, integerValue.get());
                } else {
                    inputMemory.setString(triple.attribute, triple.value);
                }

                publishedQMemoryPaths.add(triple.attribute);

                System.out.println("[QMemory] scheduled input-link ^"
                        + triple.attribute + " " + triple.value);
            }

            inputMemory.setInteger("event-id", nextEventId);
            publishedQMemoryPaths.add("event-id");

            System.out.println("[QMemory] scheduled input-link ^event-id " + nextEventId);
        }

        this.agent.getAgent().getInputOutput().asynchronousInputReady();

        System.out.println("[PendingInput] QMemory updated; waiting for next InputEvent; event-id="
                + nextEventId);
    }

    private void publishSnapshotToQMemory(Set<InputTriple> snapshot, long eventIdSnapshot) {
        if (inputMemory == null) {
            throw new IllegalStateException("Input QMemory has not been initialized yet.");
        }

        synchronized (inputMemory) {
            for (String oldPath : publishedQMemoryPaths) {
                inputMemory.remove(oldPath);
            }
            publishedQMemoryPaths.clear();

            for (InputTriple triple : snapshot) {
                final String path = sanitizeQMemoryPath(triple.attribute);
                final String value = triple.value.trim();

                if (path.isBlank() || value.isBlank()) {
                    continue;
                }

                final Optional<Long> integerValue = parseLong(value);
                if (integerValue.isPresent()) {
                    inputMemory.setInteger(path, integerValue.get());
                } else {
                    inputMemory.setString(path, value);
                }

                publishedQMemoryPaths.add(path);

                System.out.println("[QMemoryInput] input-link ^" + path + " " + value);
            }

            inputMemory.setInteger("event-id", eventIdSnapshot);
            publishedQMemoryPaths.add("event-id");

            System.out.println("[QMemoryInput] input-link ^event-id " + eventIdSnapshot);
        }

        this.agent.getAgent().getInputOutput().asynchronousInputReady();
    }

    private static Optional<Long> parseLong(String value) {
        try {
            return Optional.of(Long.parseLong(value.trim()));
        } catch (NumberFormatException ignored) {
            return Optional.empty();
        }
    }

    private static String sanitizeQMemoryPath(String attribute) {
        /*
         * QMemory uses dots to represent nested WM paths. For the current use case,
         * direct input-link augmentations are desired, e.g. ^predicate and ^value.
         * If an annotation accidentally contains whitespace or leading ^, normalize it.
         */
        return attribute.trim()
                .replaceFirst("^\\^+", "")
                .replaceAll("\\s+", "-");
    }

    private void startWebServer(int port) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);

        server.createContext("/annotations", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            try (InputStream requestBody = exchange.getRequestBody()) {
                final Model model = Rio.parse(requestBody, "", RDFFormat.JSONLD);
                //System.out.println("[DEBUG HTTP] before agent.execute for annotation");
                this.agent.execute(
                        () -> {
                            /*System.out.println("[DEBUG AGENT THREAD] entered annotation callable; isAgentThread="
                                    + this.agent.isAgentThread()
                                    + "; isRunning="
                                    + this.agent.isRunning());*/

                            processAnnotationInformation(model);

                            //System.out.println("[DEBUG AGENT THREAD] leaving annotation callable");
                            return null;
                        },
                        result -> {
                            /*System.out.println("[DEBUG COMPLETION] annotation callable completed; isRunning="
                                    + this.agent.isRunning());*/

                            if (!this.agent.isRunning()) {
                                //System.out.println("[DEBUG COMPLETION] Agent was stopped after input update; scheduling run on helper thread.");

                                new Thread(() -> {
                                    System.out.println("[DEBUG RUN THREAD] running 5 decisions; isAgentThread="
                                            + this.agent.isAgentThread()
                                            + "; isRunning="
                                            + this.agent.isRunning());

                                    this.agent.runFor(5, org.jsoar.kernel.RunType.DECISIONS);
                                }, "soar-input-restart").start();
                            } else {
                                //System.out.println("[DEBUG COMPLETION] The agent is still running");
                            }
                        });

                //System.out.println("[DEBUG HTTP] after agent.execute for annotation");
                exchange.sendResponseHeaders(202, 0);
            } catch (Exception e) {
                System.err.println("Failed to process incoming annotation: " + e.getMessage());
                final byte[] err = e.getMessage().getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(400, err.length);
                exchange.getResponseBody().write(err);
            } finally {
                exchange.getResponseBody().close();
            }
        });

        server.createContext("/profile", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            final Model snapshot;
            synchronized (profileLock) {
                snapshot = new LinkedHashModel(agentProfile);
            }

            final byte[] turtle = serializeAsTurtle(snapshot).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/turtle; charset=utf-8");
            exchange.sendResponseHeaders(200, turtle.length);
            exchange.getResponseBody().write(turtle);
            exchange.getResponseBody().close();
        });

        server.createContext("/ontology", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            final byte[] turtle = serializeAsTurtle(buildOntologyModel()).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/turtle; charset=utf-8");
            exchange.sendResponseHeaders(200, turtle.length);
            exchange.getResponseBody().write(turtle);
            exchange.getResponseBody().close();
        });

        server.createContext("/ontologies/soar", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            final byte[] turtle = serializeAsTurtle(buildSoarOntologyModel()).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/turtle; charset=utf-8");
            exchange.sendResponseHeaders(200, turtle.length);
            exchange.getResponseBody().write(turtle);
            exchange.getResponseBody().close();
        });

        server.createContext("/message", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            try {
                final byte[] body = exchange.getRequestBody().readAllBytes();
                final String json = new String(body, StandardCharsets.UTF_8).trim();
                final JSONObject msg = new JSONObject(json);
                this.agent.execute(() -> applyMessageToPerceivedInput(msg));
                exchange.sendResponseHeaders(202, 0);
            } catch (Exception e) {
                System.err.println("Failed to process /message: " + e.getMessage());
                final byte[] err = e.getMessage().getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(400, err.length);
                exchange.getResponseBody().write(err);
            } finally {
                exchange.getResponseBody().close();
            }
        });

        server.createContext("/gui", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            final byte[] html = buildGuiHtml().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
            exchange.sendResponseHeaders(200, html.length);
            exchange.getResponseBody().write(html);
            exchange.getResponseBody().close();
        });

        server.createContext("/gui/state", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            String json;
            try {
                json = buildStateJson();
            } catch (Exception e) {
                json = "{\"error\":\"" + escapeJson(String.valueOf(e.getMessage())) + "\"}";
            }

            final byte[] data = json.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, data.length);
            exchange.getResponseBody().write(data);
            exchange.getResponseBody().close();
        });

        server.createContext("/gui/wm", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, 0);
                exchange.getResponseBody().close();
                return;
            }

            final String text = buildWorkingMemoryText();
            final byte[] data = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
            exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, data.length);
            exchange.getResponseBody().write(data);
            exchange.getResponseBody().close();
        });

        server.setExecutor(null);
        server.start();
        System.out.println("Web server started on port " + port);
    }

    private String buildWorkingMemoryText() {
        final AtomicReference<String> result = new AtomicReference<>("");
        final CountDownLatch done = new CountDownLatch(1);

        this.agent.execute(() -> {
            try {
                final StringBuilder sb = new StringBuilder();
                final Set<Wme> wmes = this.agent.getAgent().getAllWmesInRete();

                sb.append("# Working memory from agent.getAllWmesInRete()")
                        .append(System.lineSeparator());
                sb.append("# WME count: ")
                        .append(wmes.size())
                        .append(System.lineSeparator())
                        .append(System.lineSeparator());

                for (final Wme wme : wmes) {
                    sb.append(wme.toString())
                            .append(System.lineSeparator());
                }

                synchronized (perceivedInputLock) {
                    sb.append(System.lineSeparator())
                            .append("# Pending perceived-input snapshot")
                            .append(System.lineSeparator());
                    sb.append("# perceivedInputEventId: ")
                            .append(perceivedInputEventId)
                            .append(System.lineSeparator());

                    for (InputTriple triple : perceivedInputTriples) {
                        sb.append("# pending input-link ^")
                                .append(triple.attribute)
                                .append(" ")
                                .append(triple.value)
                                .append(System.lineSeparator());
                    }
                }

                if (inputMemory != null) {
                    synchronized (inputMemory) {
                        sb.append(System.lineSeparator())
                                .append("# QMemory input source")
                                .append(System.lineSeparator());

                        for (Object pathObj : inputMemory.getPaths()) {
                            final String path = String.valueOf(pathObj);
                            sb.append("# qmemory ")
                                    .append(path)
                                    .append(" = ")
                                    .append(inputMemory.getString(path))
                                    .append(System.lineSeparator());
                        }
                    }
                }

                result.set(sb.toString());
            } catch (Exception e) {
                result.set("# Failed to read working memory: "
                        + e.getMessage()
                        + System.lineSeparator());
            } finally {
                done.countDown();
            }
        });

        try {
            if (!done.await(2, TimeUnit.SECONDS)) {
                return "# Timed out while reading working memory." + System.lineSeparator();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "# Interrupted while reading working memory." + System.lineSeparator();
        }

        return result.get();
    }

    private void handleRegisterProfile(Identifier command) {
        try {
            final String profileUrl = requireCommandValue(command, "profile-url");
            final String tdUrl = getCommandValue(command, "td-url");

            if (tdUrl != null) {
                System.out.println("register-profile via TD discovery: " + tdUrl);
                try {
                    final AffordanceTarget target = resolveAffordance(
                            tdUrl, "hmas:registerProfile", "https://purl.org/hmas/registerProfile");
                    final String body = "{\"name\":\"" + escapeJson(SETUP4_PROFILE_REGISTRATION_NAME)
                            + "\",\"url\":\"" + escapeJson(profileUrl) + "\"}";
                    final Map<String, String> headers = new LinkedHashMap<>();
                    headers.put("Content-Type", "application/json");

                    final int code = sendRequestPayload(target.href, target.method, headers, body);
                    if (code >= 200 && code < 300) {
                        System.out.println("register-profile success: " + code);
                    } else {
                        System.err.println("register-profile failed with status: " + code);
                    }
                } catch (Exception e) {
                    System.err.println("register-profile failed: " + e.getMessage());
                    e.printStackTrace();
                }
                return;
            }

            final String serverUrl = requireCommandValue(command, "server-url");
            System.out.println("register-profile via legacy server: " + serverUrl);

            final Map<String, String> headers = new LinkedHashMap<>();
            headers.put("Content-Type", "application/json");

            final String body = "{\"name\":\"" + escapeJson(SETUP4_PROFILE_REGISTRATION_NAME)
                    + "\",\"url\":\"" + escapeJson(profileUrl) + "\"}";
            final int code = sendRequestPayload(serverUrl, "POST", headers, body);

            if (code >= 200 && code < 300) {
                System.out.println("register-profile success: " + code);
            } else {
                System.err.println("register-profile failed with status: " + code);
            }
        } catch (Exception e) {
            System.err.println("register-profile command error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void handleQueryAnnotations(Identifier command) {
        try {
            final String tdUrl = requireCommandValue(command, "td-url");
            final String profileUrl = requireCommandValue(command, "profile-url");

            System.out.println("query-annotations via TD: " + tdUrl);

            try {
                final AffordanceTarget target = resolveAffordance(
                        tdUrl, "hmas:queryAnnotations", "https://purl.org/hmas/queryAnnotations");

                final String encoded = URLEncoder.encode(profileUrl, StandardCharsets.UTF_8);
                final String queryUrl = target.href.contains("?")
                        ? target.href + "&profile=" + encoded
                        : target.href + "?profile=" + encoded;

                final HttpClient client = HttpClient.newHttpClient();
                final HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(queryUrl))
                        .header("Accept", "text/turtle, application/ld+json")
                        .GET()
                        .build();

                final var response = client.send(request, BodyHandlers.ofString());
                System.out.println("query-annotations status: " + response.statusCode());

                if (response.statusCode() == 404) {
                    System.out.println("query-annotations: no annotations found (404)");
                    return;
                }

                if (response.statusCode() >= 200 && response.statusCode() < 300) {
                    final String ct = response.headers()
                            .firstValue("Content-Type")
                            .orElse("text/turtle");
                    final RDFFormat fmt = ct.contains("json") ? RDFFormat.JSONLD : RDFFormat.TURTLE;

                    final Model model = Rio.parse(
                            new ByteArrayInputStream(response.body().getBytes(StandardCharsets.UTF_8)),
                            "",
                            fmt);

                    this.agent.execute(() -> processAnnotationInformation(model));
                } else {
                    System.err.println("query-annotations failed with status: " + response.statusCode());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.err.println("query-annotations interrupted: " + e.getMessage());
            } catch (Exception e) {
                System.err.println("query-annotations failed: " + e.getMessage());
                e.printStackTrace();
            }
        } catch (Exception e) {
            System.err.println("query-annotations command error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void handleSendHttpRequest(Identifier command) {
        try {
            final String method = requireCommandValue(command, "method");
            final String url = requireCommandValue(command, "url");
            final String headersJson = getCommandValue(command, "headers");
            final String payload = getCommandValue(command, "payload");

            System.out.println("send-http-request: " + method + " " + url);

            final Map<String, String> headers = new LinkedHashMap<>();
            headers.put("Content-Type", "application/json");

            if (headersJson != null && !headersJson.isBlank()) {
                try {
                    final JSONObject obj = new JSONObject(headersJson);
                    for (final String key : obj.keySet()) {
                        headers.put(key, obj.getString(key));
                    }
                } catch (Exception e) {
                    System.err.println("send-http-request: invalid headers JSON: " + e.getMessage());
                }
            }

            final int code = sendRequestPayload(url, method, headers, payload != null ? payload : "");

            if (code >= 200 && code < 300) {
                System.out.println("send-http-request success: " + code);
            } else {
                System.err.println("send-http-request failed with status: " + code);
            }
        } catch (Exception e) {
            System.err.println("send-http-request error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void handleSetGoal(Identifier command) {
        try {
            final String goalType = requireCommandValue(command, "goal-type");
            final IRI goalTypeIri = rdf.createIRI(getSoarOntologyBase() + goalType);

            synchronized (profileLock) {
                final Resource goalNode = rdf.createBNode();
                agentProfile.add(agentId, HMAS.hasGoal, goalNode);
                agentProfile.add(goalNode, RDF.TYPE, goalTypeIri);
            }

            System.out.println("set-goal success: " + goalType);
        } catch (Exception e) {
            System.err.println("set-goal error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void handleClearGoal(Identifier command) {
        try {
            final String goalType = getCommandValue(command, "goal-type");

            synchronized (profileLock) {
                if (goalType != null) {
                    final IRI goalTypeIri = rdf.createIRI(getSoarOntologyBase() + goalType);
                    final Set<Resource> toRemove = new LinkedHashSet<>();

                    for (final Statement s : agentProfile.filter(agentId, HMAS.hasGoal, null)) {
                        if (s.getObject() instanceof Resource goalNode
                                && !agentProfile.filter(goalNode, RDF.TYPE, goalTypeIri).isEmpty()) {
                            toRemove.add(goalNode);
                        }
                    }

                    for (final Resource goalNode : toRemove) {
                        agentProfile.remove(agentId, HMAS.hasGoal, goalNode);
                        agentProfile.remove(goalNode, null, null);
                    }

                    System.out.println("clear-goal success: cleared " + goalType);
                } else {
                    final Set<Resource> allGoals = new LinkedHashSet<>();

                    for (final Statement s : agentProfile.filter(agentId, HMAS.hasGoal, null)) {
                        if (s.getObject() instanceof Resource r) {
                            allGoals.add(r);
                        }
                    }

                    agentProfile.remove(agentId, HMAS.hasGoal, null);

                    for (final Resource goalNode : allGoals) {
                        agentProfile.remove(goalNode, null, null);
                    }

                    System.out.println("clear-goal success: cleared all " + allGoals.size() + " goals");
                }
            }
        } catch (Exception e) {
            System.err.println("clear-goal error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void handleSetAgentGoal(Identifier command) {
        try {
            final String goalUriString = requireCommandValue(command, "goal-uri");
            final IRI newGoalIri = rdf.createIRI(goalUriString);

            System.out.println("set-agent-goal: " + goalUriString);

            synchronized (profileLock) {
                final Set<Resource> oldGoalNodes = new LinkedHashSet<>();

                for (final Statement s : agentProfile.filter(agentId, HMAS.hasGoal, null)) {
                    if (s.getObject() instanceof Resource goalNode) {
                        oldGoalNodes.add(goalNode);
                    }
                }

                for (final Resource goalNode : oldGoalNodes) {
                    agentProfile.remove(agentId, HMAS.hasGoal, goalNode);
                    agentProfile.remove(goalNode, null, null);
                }

                final Resource newGoalNode = rdf.createBNode();
                agentProfile.add(agentId, HMAS.hasGoal, newGoalNode);
                agentProfile.add(newGoalNode, RDF.TYPE, newGoalIri);
            }

            System.out.println("set-agent-goal success: updated profile to " + goalUriString);
        } catch (Exception e) {
            System.err.println("set-agent-goal error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void handleSendMessage(Identifier command) {
        try {
            final String receiverUrl = requireCommandValue(command, "url");
            final String tdUrl = requireCommandValue(command, "td-url");

            final Model messageModel = createSendMessageModel(command, receiverUrl);
            final String messageJson = writeAsJsonLd(messageModel);
            final String payloadJson = "{\"agent\":\"" + escapeJson(receiverUrl)
                    + "\",\"message\":" + messageJson + "}";

            final String directUrl = URI.create(tdUrl).resolve("messages").toString();
            System.out.println("send-message → " + directUrl + " for " + receiverUrl);

            final Map<String, String> headers = new LinkedHashMap<>();
            headers.put("Content-Type", "application/json");

            final int code = sendRequestPayload(directUrl, "POST", headers, payloadJson);

            if (code >= 200 && code < 300) {
                System.out.println("send-message success: " + code);
            } else {
                System.err.println("send-message failed with status: " + code);
            }
        } catch (Exception e) {
            System.err.println("send-message error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private Model createSendMessageModel(Identifier command, String receiverUrl) {
        final Model model = new LinkedHashModel();
        final Resource messageId = rdf.createIRI("http://example.org/messages/" + UUID.randomUUID());
        final Resource abilityNode = rdf.createBNode();
        final Resource contentNode = rdf.createBNode();

        model.add(messageId, RDF.TYPE, HMAS.Message);
        model.add(messageId, HMAS.hasId, rdf.createLiteral(UUID.randomUUID().toString()));
        model.add(messageId, HMAS.hasSender, agentId);
        model.add(messageId, HMAS.hasReceiver, rdf.createIRI(receiverUrl));
        model.add(messageId, HMAS.recommendsAbility, abilityNode);
        model.add(abilityNode, RDF.TYPE, SoarOnt.soar_light_processing);
        model.add(messageId, HMAS.conveys, contentNode);

        final String done = getCommandValue(command, "done");
        if (done != null) {
            model.add(contentNode, SoarOnt.done, rdf.createLiteral(done));
        }

        final String reason = getCommandValue(command, "reason");
        if (reason != null) {
            model.add(contentNode, SoarOnt.reason, rdf.createLiteral(reason));
        }

        final String eventId = getCommandValue(command, "event-id");
        if (eventId != null) {
            model.add(contentNode, SoarOnt.eventId, rdf.createLiteral(eventId));
        }

        final String goalZ1 = getCommandValue(command, "goal-z1");
        if (goalZ1 != null) {
            model.add(contentNode, SoarOnt.goalZ1, rdf.createLiteral(goalZ1));
        }

        final String goalZ2 = getCommandValue(command, "goal-z2");
        if (goalZ2 != null) {
            model.add(contentNode, SoarOnt.goalZ2, rdf.createLiteral(goalZ2));
        }

        return model;
    }

    private void applyMessageToPerceivedInput(JSONObject msg) {
        final Set<InputTriple> triples = new LinkedHashSet<>();

        for (final String key : msg.keySet()) {
            if ("attribute".equals(key)) {
                continue;
            }

            final String value = msg.optString(key, "").trim();
            if (!key.isBlank() && !value.isBlank()) {
                triples.add(new InputTriple(key, value));
            }
        }

        if (triples.isEmpty()) {
            final String attribute = msg.optString("attribute", "").trim();
            final String value = msg.optString("value", "").trim();

            if (!attribute.isBlank() && !value.isBlank()) {
                triples.add(new InputTriple(attribute, value));
            }
        }

        if (triples.isEmpty()) {
            System.out.println("[message] No publishable input triples.");
            return;
        }

        for (InputTriple triple : triples) {
            System.out.println("[PendingInput/message] input-link ^"
                    + triple.attribute + " " + triple.value);
        }

        setPerceivedInputTriples(triples);
    }

    private List<Map.Entry<String, String>> readEntries(Identifier command) {
        final List<Map.Entry<String, String>> entries = new ArrayList<>();
        final Identifier list = requireIdentifierValue(command, "list");

        for (Identifier entry : getChildren(list, "element")) {
            final String key = requireCommandValue(entry, "first");
            final String value = requireCommandValue(entry, "second");
            entries.add(Map.entry(key, value));
        }

        return entries;
    }

    private List<Identifier> getChildren(Identifier parent, String attribute) {
        final List<Identifier> children = new ArrayList<>();
        final org.jsoar.kernel.symbols.Symbol expectedAttribute =
                this.agent.getSymbols().createString(attribute);

        for (var it = parent.getWmes(); it.hasNext();) {
            final Wme wme = it.next();
            if (!wme.getAttribute().equals(expectedAttribute)) {
                continue;
            }

            final Identifier child = wme.getValue().asIdentifier();
            if (child != null) {
                children.add(child);
            }
        }

        return children;
    }

    private String requireCommandValue(Identifier identifier, String attribute) {
        final String value = getCommandValue(identifier, attribute);

        if (value == null) {
            throw new IllegalStateException(
                    "Missing required command attribute '" + attribute + "' on " + identifier);
        }

        return value;
    }

    private Identifier requireIdentifierValue(Identifier identifier, String attribute) {
        final Identifier value = getIdentifierValue(identifier, attribute);

        if (value == null) {
            throw new IllegalStateException(
                    "Missing required identifier attribute '" + attribute + "' on " + identifier);
        }

        return value;
    }

    private String getCommandValue(Identifier identifier, String attribute) {
        final org.jsoar.kernel.symbols.Symbol expectedAttribute =
                this.agent.getSymbols().createString(attribute);

        for (var it = identifier.getWmes(); it.hasNext();) {
            final Wme wme = it.next();
            if (wme.getAttribute().equals(expectedAttribute)) {
                return wme.getValue().toString();
            }
        }

        return null;
    }

    private Identifier getIdentifierValue(Identifier identifier, String attribute) {
        final org.jsoar.kernel.symbols.Symbol expectedAttribute =
                this.agent.getSymbols().createString(attribute);

        for (var it = identifier.getWmes(); it.hasNext();) {
            final Wme wme = it.next();
            if (wme.getAttribute().equals(expectedAttribute)) {
                return wme.getValue().asIdentifier();
            }
        }

        return null;
    }

    private void processAnnotationInformation(Model model) {
        final Set<Resource> annotations = new LinkedHashSet<>();

        for (Statement statement : model.filter(null, RDF.TYPE, HMAS.Annotation)) {
            if (statement.getSubject() instanceof Resource resource) {
                annotations.add(resource);
            }
        }

        System.out.println("[read-annotations] Number of annotations found: " + annotations.size());

        if (annotations.isEmpty()) {
            return;
        }

        final List<Resource> addWmeActions = new ArrayList<>();

        for (Resource annotation : annotations) {
            final String annotationId = getAnnotationId(annotation, model);

            synchronized (annotationLock) {
                if (annotationId != null && processedAnnotationIds.contains(annotationId)) {
                    System.out.println("[read-annotations] Skipping already-processed annotation: " + annotationId);
                    continue;
                }

                if (annotationId != null) {
                    processedAnnotationIds.add(annotationId);
                }
            }

            for (Statement statement : model.filter(annotation, HMAS.conveys, null)) {
                if (statement.getObject() instanceof Resource action
                        && !model.filter(action, RDF.TYPE, SoarOnt.AddWME).isEmpty()) {
                    addWmeActions.add(action);
                }
            }
        }

        if (addWmeActions.isEmpty()) {
            System.out.println("[read-annotations] No AddWME actions found.");
            return;
        }

        final Set<InputTriple> triplesToPublish = new LinkedHashSet<>();

        for (Resource action : addWmeActions) {
            final Value inputLinkValue = getModelValue(action, SoarOnt.hasInputLink, model);

            if (!(inputLinkValue instanceof Resource inputLinkResource)) {
                System.out.println("[read-signifiers] Skipping action: no hasInputLink.");
                continue;
            }

            final List<Resource> relations = new ArrayList<>();

            for (Statement relationStatement : model.filter(action, SoarOnt.hasRelation, null)) {
                if (relationStatement.getObject() instanceof Resource relation) {
                    relations.add(relation);
                }
            }

            if (relations.isEmpty()) {
                System.out.println("[read-signifiers] Skipping action: no relations attached.");
                continue;
            }

            for (Resource relation : relations) {
                final Value identifierValue = getModelValue(relation, SoarOnt.hasIdentifier, model);

                if (!(identifierValue instanceof Resource parentResource)) {
                    System.out.println("[read-signifiers] Relation missing hasIdentifier; skipping.");
                    continue;
                }

                /*
                 * This version publishes only direct literal augmentations of the input-link:
                 *
                 *   input-link ^predicate light
                 *   input-link ^value on
                 *
                 * Nested identifier-valued input can be added later by mapping RDF resources
                 * to QMemory paths such as action.method, action.url, etc.
                 */
                if (!parentResource.equals(inputLinkResource)) {
                    System.out.println("[read-signifiers] Relation is not directly on input-link; skipping: "
                            + parentResource);
                    continue;
                }

                final Optional<Literal> attributeLiteral =
                        asLiteral(getModelValue(relation, SoarOnt.hasAttribute, model), model);

                if (attributeLiteral.isEmpty()) {
                    System.out.println("[read-signifiers] Relation missing/invalid hasAttribute; skipping.");
                    continue;
                }

                final Value rawValue = getModelValue(relation, SoarOnt.hasValue, model);

                if (rawValue == null) {
                    System.out.println("[read-signifiers] Relation missing hasValue; skipping.");
                    continue;
                }

                final Optional<Literal> valueLiteral = asLiteral(rawValue, model);

                if (valueLiteral.isEmpty()) {
                    System.out.println("[read-signifiers] Relation value is not a literal; skipping.");
                    continue;
                }

                final String attribute = sanitizeQMemoryPath(attributeLiteral.get().getLabel());
                final String value = valueLiteral.get().getLabel().trim();

                if (attribute.isBlank()) {
                    System.out.println("[read-signifiers] Empty attribute; skipping.");
                    continue;
                }

                if (value.isBlank()) {
                    System.out.println("[read-signifiers] Empty value for ^" + attribute + "; skipping.");
                    continue;
                }

                final InputTriple triple = new InputTriple(attribute, value);

                if (triplesToPublish.add(triple)) {
                    System.out.println("[PendingInput] input-link ^" + attribute + " " + value);
                } else {
                    System.out.println("[PendingInput] duplicate ignored: input-link ^"
                            + attribute + " " + value);
                }
            }
        }

        if (triplesToPublish.isEmpty()) {
            System.out.println("[read-signifiers] No publishable input-link triples extracted.");
            return;
        }

        setPerceivedInputTriples(triplesToPublish);
    }

    private String getAnnotationId(Resource annotation, Model model) {
        for (Statement statement : model.filter(annotation, HMAS.hasId, null)) {
            Value obj = statement.getObject();
            if (obj instanceof Literal lit) {
                return lit.getLabel();
            }
        }

        return null;
    }

    private Value getModelValue(Resource resource, IRI iri, Model model) {
        for (Statement statement : model.filter(resource, iri, null)) {
            return statement.getObject();
        }

        return null;
    }

    private Optional<Literal> asLiteral(Value value, Model model) {
        if (value instanceof Literal literal) {
            return Optional.of(literal);
        }

        if (value instanceof Resource resource) {
            for (Statement statement : model.filter(resource, SoarOnt.hasLiteral, null)) {
                if (statement.getObject() instanceof Literal literal) {
                    return Optional.of(literal);
                }
            }
        }

        return Optional.empty();
    }

    private Identifier getOrCreateIdentifier(
            Resource resource,
            Map<Resource, Identifier> identifierByResource,
            Model model) {
        final Identifier existing = identifierByResource.get(resource);

        if (existing != null) {
            return existing;
        }

        char prefix = 'E';
        final Optional<Literal> nameLiteral = asLiteral(resource, model);

        if (nameLiteral.isPresent() && !nameLiteral.get().getLabel().isEmpty()) {
            prefix = Character.toUpperCase(nameLiteral.get().getLabel().charAt(0));
        }

        final Identifier created = this.agent.getSymbols().createIdentifier(prefix);
        identifierByResource.put(resource, created);

        return created;
    }

    private record AffordanceTarget(String href, String method) {}

    private AffordanceTarget resolveAffordance(String tdUrl, String compactType, String iriType) throws IOException {
        try {
            final HttpClient client = HttpClient.newHttpClient();
            final HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(tdUrl))
                    .header("Accept", "application/td+json, application/json")
                    .GET()
                    .build();

            final var response = client.send(request, BodyHandlers.ofString());
            final JSONObject td = new JSONObject(response.body());
            final JSONObject actions = td.optJSONObject("actions");

            if (actions == null) {
                throw new IOException("TD at " + tdUrl + " has no 'actions'");
            }

            for (final String key : actions.keySet()) {
                final JSONObject action = actions.optJSONObject(key);

                if (action == null || !hasAffordanceType(action, compactType, iriType)) {
                    continue;
                }

                final JSONArray forms = action.optJSONArray("forms");
                if (forms == null || forms.isEmpty()) {
                    continue;
                }

                final JSONObject form = forms.getJSONObject(0);
                final String href = form.getString("href");
                final String method = form.optString("htv:methodName", "POST");
                final String resolved = URI.create(tdUrl).resolve(href).toString();

                return new AffordanceTarget(resolved, method);
            }

            throw new IOException("No affordance " + compactType + " in TD at " + tdUrl);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("Interrupted resolving affordance from " + tdUrl, e);
        }
    }

    private boolean hasAffordanceType(JSONObject action, String compactType, String iriType) {
        final Object typeValue = action.opt("@type");

        if (typeValue instanceof JSONArray arr) {
            for (int i = 0; i < arr.length(); i++) {
                final String v = arr.optString(i);

                if (compactType.equals(v) || iriType.equals(v)) {
                    return true;
                }
            }

            return false;
        }

        if (typeValue instanceof String s) {
            return compactType.equals(s) || iriType.equals(s);
        }

        return false;
    }

    private Model buildOntologyModel() {
        final IRI rdfsClass = rdf.createIRI("http://www.w3.org/2000/01/rdf-schema#Class");
        final IRI rdfsComment = rdf.createIRI("http://www.w3.org/2000/01/rdf-schema#comment");
        final IRI rdfsProperty = rdf.createIRI("http://www.w3.org/2000/01/rdf-schema#Property");

        final ModelBuilder b = new ModelBuilder();

        b.add(SoarOnt.soar_ability, RDF.TYPE, rdfsClass);
        b.add(SoarOnt.soar_ability, rdfsComment, rdf.createLiteral("Base Soar agent ability.", "en"));

        b.add(SoarOnt.soar_light_processing, RDF.TYPE, rdfsClass);
        b.add(SoarOnt.soar_light_processing, rdfsComment,
                rdf.createLiteral("Ability to process state(Z1,Z2) goals for the light-processing agent.", "en"));

        b.add(SoarOnt.WMETurn, RDF.TYPE, rdfsClass);
        b.add(SoarOnt.WMETurn, rdfsComment,
                rdf.createLiteral("Ability to process turn-on/turn-off AddWME annotations.", "en"));


        b.add(SoarOnt.predicate, RDF.TYPE, rdfsProperty);
        b.add(SoarOnt.predicate, rdfsComment,
                rdf.createLiteral("Functor name of a WME-encoded predicate.", "en"));

        b.add(SoarOnt.done, RDF.TYPE, rdfsProperty);
        b.add(SoarOnt.done, rdfsComment,
                rdf.createLiteral("Completion flag emitted by the light-processing Soar agent.", "en"));

        return b.build();
    }

    private String getSoarOntologyBase() {
        return "http://localhost:" + DEFAULT_WEB_SERVER_PORT + "/soar#";
    }

    private Model buildSoarOntologyModel() {
        final String soarBase = getSoarOntologyBase();

        final IRI rdfsClass = rdf.createIRI("http://www.w3.org/2000/01/rdf-schema#Class");
        final IRI rdfsComment = rdf.createIRI("http://www.w3.org/2000/01/rdf-schema#comment");
        final IRI rdfsProp = rdf.createIRI("http://www.w3.org/2000/01/rdf-schema#Property");

        final ModelBuilder b = new ModelBuilder();

        final IRI soarAbility = rdf.createIRI(soarBase + "soar_ability");
        final IRI soarLightProcessing = rdf.createIRI(soarBase + "soar_light_processing");
        final IRI predicate = rdf.createIRI(soarBase + "predicate");
        final IRI idx = rdf.createIRI(soarBase + "idx");
        final IRI hasIdentifier = rdf.createIRI(soarBase + "hasIdentifier");
        final IRI hasAttribute = rdf.createIRI(soarBase + "hasAttribute");
        final IRI hasValue = rdf.createIRI(soarBase + "hasValue");
        final IRI hasLiteral = rdf.createIRI(soarBase + "hasLiteral");
        final IRI hasInputLink = rdf.createIRI(soarBase + "hasInputLink");
        final IRI hasRelation = rdf.createIRI(soarBase + "hasRelation");
        final IRI done = rdf.createIRI(soarBase + "done");
        final IRI addWME = rdf.createIRI(soarBase + "AddWME");

        b.add(soarAbility, RDF.TYPE, rdfsClass);
        b.add(soarAbility, rdfsComment, rdf.createLiteral("Base Soar agent ability.", "en"));

        b.add(soarLightProcessing, RDF.TYPE, rdfsClass);
        b.add(soarLightProcessing, rdfsComment,
                rdf.createLiteral("Ability to process state(Z1,Z2) goals for the light-processing agent.", "en"));


        b.add(predicate, RDF.TYPE, rdfsProp);
        b.add(predicate, rdfsComment,
                rdf.createLiteral("Functor name of a WME-encoded predicate.", "en"));
        b.add(idx, RDF.TYPE, rdfsProp);
        b.add(hasIdentifier, RDF.TYPE, rdfsProp);
        b.add(hasAttribute, RDF.TYPE, rdfsProp);
        b.add(hasValue, RDF.TYPE, rdfsProp);
        b.add(hasLiteral, RDF.TYPE, rdfsProp);
        b.add(hasInputLink, RDF.TYPE, rdfsProp);
        b.add(hasRelation, RDF.TYPE, rdfsProp);
        b.add(done, RDF.TYPE, rdfsProp);
        b.add(done, rdfsComment,
                rdf.createLiteral("Completion flag emitted by the light-processing Soar agent.", "en"));
        b.add(addWME, RDF.TYPE, rdfsClass);

        return b.build();
    }

    private String writeAsJsonLd(Model model) {
        final OutputStream out = new ByteArrayOutputStream();

        try {
            Rio.write(model, out, RDFFormat.JSONLD,
                    new WriterConfig().set(BasicWriterSettings.INLINE_BLANK_NODES, true));
            return out.toString();
        } finally {
            try {
                out.close();
            } catch (IOException e) {
                throw new IllegalStateException("Failed closing JSON-LD buffer", e);
            }
        }
    }

    private void postJsonLdHttpRequest(String url, String json) {
        final HttpClient client = HttpClient.newHttpClient();

        final HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/ld+json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        try {
            final var response = client.send(request, BodyHandlers.ofString());
            System.out.println("Status code: " + response.statusCode());
            System.out.println("Response body: " + response.body());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Failed posting JSON-LD to " + url, e);
        } catch (IOException e) {
            throw new IllegalStateException("Failed posting JSON-LD to " + url, e);
        }
    }

    private static int sendRequestPayload(
            String urlString,
            String method,
            Map<String, String> headers,
            String payload) {
        System.out.println("url string: " + urlString);

        final BasicClassicHttpRequest request = new BasicClassicHttpRequest(method, urlString);

        for (Map.Entry<String, String> header : headers.entrySet()) {
            request.addHeader(header.getKey(), header.getValue());
        }

        request.setEntity(new StringEntity(payload));

        try (CloseableHttpClient client = HttpClients.createDefault()) {
            final HttpResponse response = client.execute(request);
            return response.getCode();
        } catch (Exception e) {
            throw new IllegalStateException("Sending request with payload failed", e);
        }
    }

    private static String serializeAsTurtle(Model model) {
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        Rio.write(model, out, RDFFormat.TURTLE,
                new WriterConfig().set(BasicWriterSettings.PRETTY_PRINT, true)
                        .set(BasicWriterSettings.INLINE_BLANK_NODES, true));
        return out.toString(StandardCharsets.UTF_8);
    }

    private static String rstripSlash(String value) {
        if (value == null) {
            return null;
        }

        int end = value.length();

        while (end > 0 && value.charAt(end - 1) == '/') {
            end--;
        }

        return end == value.length() ? value : value.substring(0, end);
    }

    private static String escapeJson(String value) {
        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"");
    }

    public String getAgentName() {
        return this.agentName;
    }

    public ThreadedAgent getAgent() {
        return this.agent;
    }

    private String buildStateJson() {
        final JSONObject state = new JSONObject();
        state.put("agentName", agentName);
        state.put("isRunning", agent.isRunning());
        state.put("timestamp", System.currentTimeMillis());

        try {
            final Long dCycle = agent.getAgent().getProperties().get(SoarProperties.D_CYCLE_COUNT);
            state.put("dCycleCount", dCycle != null ? dCycle : 0L);
        } catch (Exception ignored) {
            state.put("dCycleCount", 0);
        }

        try {
            state.put("goalStackDepth", agent.getAgent().getGoalStack().size());
        } catch (Exception ignored) {
            state.put("goalStackDepth", 0);
        }

        final InputOutput io = agent.getAgent().getInputOutput();

        try {
            final JSONObject inputLinkJson = buildWmeNodeJson(io.getInputLink(), 0);
            state.put("inputLink", inputLinkJson != null ? inputLinkJson : JSONObject.NULL);
        } catch (Exception ignored) {
            state.put("inputLink", JSONObject.NULL);
        }

        try {
            final JSONObject outputLinkJson = buildWmeNodeJson(io.getOutputLink(), 0);
            state.put("outputLink", outputLinkJson != null ? outputLinkJson : JSONObject.NULL);
        } catch (Exception ignored) {
            state.put("outputLink", JSONObject.NULL);
        }

        final JSONArray productions = new JSONArray();

        try {
            for (final ProductionType type : ProductionType.values()) {
                for (final Production prod : agent.getAgent().getProductions().getProductions(type)) {
                    final JSONObject p = new JSONObject();
                    p.put("name", prod.getName());
                    p.put("type", type.name());
                    p.put("firings", prod.getFiringCount());
                    productions.put(p);
                }
            }
        } catch (Exception ignored) {
        }

        state.put("productions", productions);

        try {
            final DefaultSemanticMemory smem =
                    Adaptables.adapt(agent.getAgent(), DefaultSemanticMemory.class);

            if (smem != null) {
                final JSONObject smemJson = new JSONObject();
                smemJson.put("enabled", smem.smem_enabled());

                final SemanticMemoryStatistics stats = smem.getStatistics();
                smemJson.put("retrieves", stats.getRetrieves());
                smemJson.put("queries", stats.getQueries());
                smemJson.put("stores", stats.getStores());

                state.put("smem", smemJson);
            }
        } catch (Exception ignored) {
        }

        try {
            final DefaultEpisodicMemory epmem =
                    Adaptables.adapt(agent.getAgent(), DefaultEpisodicMemory.class);

            if (epmem != null) {
                final JSONObject epmemJson = new JSONObject();

                final EpisodicMemoryStatistics stats = epmem.getStats();
                epmemJson.put("time", stats.getTime());
                epmemJson.put("nextId", stats.getNextId());

                state.put("epmem", epmemJson);
            }
        } catch (Exception ignored) {
        }

        synchronized (perceivedInputLock) {
            final JSONArray pending = new JSONArray();

            for (InputTriple triple : perceivedInputTriples) {
                final JSONObject t = new JSONObject();
                t.put("attribute", triple.attribute);
                t.put("value", triple.value);
                pending.put(t);
            }

            state.put("pendingInput", pending);
            state.put("perceivedInputEventId", perceivedInputEventId);
        }

        if (inputMemory != null) {
            synchronized (inputMemory) {
                final JSONArray qmem = new JSONArray();

                for (Object pathObj : inputMemory.getPaths()) {
                    final String path = String.valueOf(pathObj);
                    final JSONObject entry = new JSONObject();
                    entry.put("path", path);
                    entry.put("value", inputMemory.getString(path));
                    qmem.put(entry);
                }

                state.put("qmemory", qmem);
            }
        }

        return state.toString();
    }

    private JSONObject buildWmeNodeJson(Identifier id, int depth) {
        if (id == null) {
            return null;
        }

        final JSONObject node = new JSONObject();
        node.put("id", id.toString());

        if (depth > 5) {
            node.put("truncated", true);
            return node;
        }

        final JSONArray wmes = new JSONArray();

        try {
            for (var it = id.getWmes(); it.hasNext();) {
                final Wme wme = it.next();
                final JSONObject w = new JSONObject();

                w.put("attr", wme.getAttribute().toString());

                final Identifier valueId = wme.getValue().asIdentifier();

                if (valueId != null) {
                    final JSONObject child = buildWmeNodeJson(valueId, depth + 1);
                    w.put("value", child != null ? child : JSONObject.NULL);
                    w.put("isId", true);
                } else {
                    w.put("value", wme.getValue().toString());
                    w.put("isId", false);
                }

                wmes.put(w);
            }
        } catch (Exception ignored) {
        }

        node.put("wmes", wmes);

        return node;
    }

    private String buildGuiHtml() {
        return """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                  <meta charset="UTF-8">
                  <meta name="viewport" content="width=device-width,initial-scale=1.0">
                  <title>Soar Monitor</title>
                  <style>
                    :root {
                      --bg: #060810; --surf: #0b0e18; --bdr: #18213a; --teal: #00e5c8;
                      --blue: #79b8ff; --green: #85e89d; --amber: #ffd580; --purple: #b392f0;
                      --text: #cdd4e2; --dim: #5c6b80; --mono: 'Courier New', monospace;
                    }
                    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
                    html, body {
                      height: 100%; overflow: hidden; background: var(--bg); color: var(--text);
                      font-family: Arial, sans-serif;
                    }
                    header {
                      height: 52px; display: flex; align-items: center; justify-content: space-between;
                      padding: 0 20px; border-bottom: 1px solid var(--bdr); background: var(--surf);
                    }
                    .logo { font-weight: 700; letter-spacing: 4px; color: var(--teal); }
                    .hright { display: flex; align-items: center; gap: 12px; }
                    .pill {
                      padding: 2px 10px; background: rgba(255,255,255,.03);
                      border: 1px solid var(--bdr); border-radius: 3px;
                      font-family: var(--mono); font-size: .7rem; color: var(--dim);
                    }
                    .pill b { color: var(--teal); }
                    main {
                      height: calc(100vh - 52px); display: grid;
                      grid-template-columns: 1fr 1fr 360px; gap: 12px; padding: 12px;
                    }
                    .panel {
                      background: var(--surf); border: 1px solid var(--bdr); border-radius: 6px;
                      display: flex; flex-direction: column; min-height: 0; overflow: hidden;
                    }
                    .panel-hd {
                      padding: 8px 12px; border-bottom: 1px solid var(--bdr); color: var(--dim);
                      font-size: .75rem; letter-spacing: 2px; text-transform: uppercase;
                    }
                    .pbody {
                      flex: 1; overflow-y: auto; padding: 8px 10px;
                      font-family: var(--mono); font-size: .78rem; line-height: 1.6;
                    }
                    .wme-children {
                      list-style: none; margin-left: 14px; border-left: 1px solid var(--bdr); padding-left: 8px;
                    }
                    details > summary { list-style: none; cursor: pointer; }
                    details > summary::-webkit-details-marker { display: none; }
                    .wid { color: var(--blue); }
                    .wat { color: var(--green); }
                    .wvs { color: var(--amber); }
                    .plist { list-style: none; }
                    .pi { display: flex; gap: 7px; padding: 3px 6px; }
                    .pt { color: var(--purple); flex-shrink: 0; }
                    .pname { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                    .pfire { color: var(--teal); }
                    .empty { color: var(--dim); padding: 16px; }
                    a { color: var(--teal); }
                  </style>
                </head>
                <body>
                <header>
                  <div class="logo">SOAR·MON</div>
                  <div class="hright">
                    <div class="pill">D-CYCLE <b id="dc">—</b></div>
                    <div class="pill">GOALS <b id="gd">—</b></div>
                    <div class="pill">STATUS <b id="status">—</b></div>
                    <div class="pill"><a href="/gui/wm" target="_blank">WM</a></div>
                  </div>
                </header>
                <main>
                  <div class="panel">
                    <div class="panel-hd">Input Link</div>
                    <div class="pbody" id="ib2"><span class="empty">loading…</span></div>
                  </div>
                  <div class="panel">
                    <div class="panel-hd">Output Link</div>
                    <div class="pbody" id="ob2"><span class="empty">loading…</span></div>
                  </div>
                  <div class="panel">
                    <div class="panel-hd">Productions / Pending Input / QMemory</div>
                    <div class="pbody" id="pb2"><span class="empty">loading…</span></div>
                  </div>
                </main>
                <script>
                  const $ = id => document.getElementById(id);

                  function esc(s) {
                    return String(s)
                      .replace(/&/g, '&amp;')
                      .replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;')
                      .replace(/"/g, '&quot;');
                  }

                  function wmeRows(node) {
                    if (!node) return '';
                    if (node.truncated) {
                      return '<li><span class="empty">' + esc(node.id) + ' [...]</span></li>';
                    }

                    return (node.wmes || []).map(w => {
                      const a = '<span class="wat">^' + esc(w.attr) + '</span>';

                      if (w.isId && w.value && typeof w.value === 'object') {
                        return '<li><details><summary>' + a + ' <span class="wid">' +
                          esc(w.value.id) + '</span></summary><ul class="wme-children">' +
                          wmeRows(w.value) + '</ul></details></li>';
                      }

                      return '<li>' + a + ' <span class="wvs">' + esc(String(w.value)) + '</span></li>';
                    }).join('');
                  }

                  function renderWme(node) {
                    if (!node) return '<div class="empty">—</div>';

                    return '<details open><summary><span class="wid">' + esc(node.id) +
                      '</span></summary><ul class="wme-children">' + wmeRows(node) + '</ul></details>';
                  }

                  function renderRightPanel(d) {
                    const prods = d.productions || [];
                    const pending = d.pendingInput || [];
                    const qmemory = d.qmemory || [];

                    let html = '';

                    html += '<div>perceivedInputEventId: <span class="wvs">' +
                      esc(d.perceivedInputEventId) + '</span></div>';

                    html += '<br><div class="wat">Pending input snapshot</div>';

                    if (pending.length) {
                      html += '<ul>' + pending.map(t =>
                        '<li>^' + esc(t.attribute) + ' ' + esc(t.value) + '</li>'
                      ).join('') + '</ul>';
                    } else {
                      html += '<div class="empty">none</div>';
                    }

                    html += '<br><div class="wat">QMemory source</div>';

                    if (qmemory.length) {
                      html += '<ul>' + qmemory.map(t =>
                        '<li>' + esc(t.path) + ' = ' + esc(t.value) + '</li>'
                      ).join('') + '</ul>';
                    } else {
                      html += '<div class="empty">none</div>';
                    }

                    html += '<br><div class="wat">Productions</div>';

                    if (!prods.length) {
                      return html + '<div class="empty">no productions loaded</div>';
                    }

                    html += '<ul class="plist">' + prods.map(p => {
                      return '<li class="pi"><span class="pt">' + esc(p.type) + '</span>' +
                        '<span class="pname" title="' + esc(p.name) + '">' + esc(p.name) + '</span>' +
                        '<span class="pfire">' + (p.firings > 0 ? p.firings + '×' : '') + '</span></li>';
                    }).join('') + '</ul>';

                    return html;
                  }

                  async function poll() {
                    try {
                      const r = await fetch('/gui/state');
                      if (!r.ok) return;

                      const d = await r.json();

                      $('dc').textContent = d.dCycleCount != null ? d.dCycleCount : '—';
                      $('gd').textContent = d.goalStackDepth != null ? d.goalStackDepth : '—';
                      $('status').textContent = d.isRunning ? 'running' : 'stopped';

                      $('ib2').innerHTML = renderWme(d.inputLink);
                      $('ob2').innerHTML = renderWme(d.outputLink);
                      $('pb2').innerHTML = renderRightPanel(d);
                    } catch (e) {
                      console.error(e);
                    }
                  }

                  poll();
                  setInterval(poll, 1000);
                </script>
                </body>
                </html>
                """;
    }

    public static void main(String[] args) {
        System.out.println("Start Soar main");

        final String agentName = args.length > 0 ? args[0] : DEFAULT_AGENT_NAME;
        final String agentSource = args.length > 1 ? args[1] : DEFAULT_AGENT_SOURCE;

        new SoarWebAgent(agentName).start(agentSource);
    }
}
