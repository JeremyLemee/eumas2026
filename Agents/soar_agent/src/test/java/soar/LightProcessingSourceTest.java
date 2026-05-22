package soar;

import org.junit.jupiter.api.Test;
import org.jsoar.kernel.Agent;
import org.jsoar.runtime.ThreadedAgent;
import soar.rhs.CountAction;
import soar.rhs.DiscretizeLightLevel;
import soar.rhs.KgActionField;
import soar.rhs.KgValue;
import soar.rhs.PrintActionHandler;
import soar.rhs.PrintList;
import soar.rhs.Stop;
import soar.rhs.StorePm;
import soar.rhs.Wait;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LightProcessingSourceTest {

    private static final Path SOURCE = Path.of("src/main/java/soar/agents/light_processing.soar");

    @Test
    void lightProcessingSourceLoadsInJSoar() throws Exception {
        final ThreadedAgent threadedAgent = ThreadedAgent.create("light-processing-source-load-test");
        final Agent agent = threadedAgent.getAgent();

        agent.getRhsFunctions().registerHandler(new PrintActionHandler());
        new CountAction().setAgent(agent);
        agent.getRhsFunctions().registerHandler(new DiscretizeLightLevel(agent));
        agent.getRhsFunctions().registerHandler(new KgValue(agent));
        agent.getRhsFunctions().registerHandler(new KgActionField(agent));
        new PrintList().setAgent(agent);
        new Wait().setAgent(agent);
        new Stop().setAgent(agent);
        new StorePm().setAgent(agent);

        threadedAgent.getInterpreter().source(SOURCE.toFile());
    }

    @Test
    void definesAllDeviceConfigurationsForFallbackSearch() throws IOException {
        final String source = Files.readString(SOURCE);

        for (int i = 0; i < 16; i++) {
            assertTrue(source.contains("^config-id c" + i), "missing config c" + i);
        }

        assertEquals(16, count(source, "^config-id c"));
        assertTrue(source.contains("light-processing*propose*fail-goal-all-configs-tried"));
    }

    @Test
    void configurationSearchCanToggleEveryDevice() throws IOException {
        final String source = Files.readString(SOURCE);

        assertTrue(source.contains("light-processing*propose*config-action-l1"));
        assertTrue(source.contains("light-processing*propose*config-action-l2"));
        assertTrue(source.contains("light-processing*propose*config-action-b1"));
        assertTrue(source.contains("light-processing*propose*config-action-b2"));
        assertTrue(source.contains("light-processing*prefer*heuristic-action-over-select-config-increase"));
        assertTrue(source.contains("light-processing*prefer*heuristic-action-over-select-config-decrease"));
        assertTrue(source.contains("^next-config-rank 0"));
        assertTrue(source.contains("light-processing*prefer*config-action-over-abandon"));
    }

    @Test
    void heuristicActionsRequireEnabledDeviceStatus() throws IOException {
        final String source = Files.readString(SOURCE);

        assertTrue(source.contains("light-processing*normalize*device-b1-status-local"));
        assertEquals(4, count(source, "^status-local <status-attribute>"));
        assertEquals(4, count(source, "^<status-attribute> true"));
    }

    @Test
    void settleWaitDoesNotDominateExecutableProgress() throws IOException {
        final String source = Files.readString(SOURCE);

        assertFalse(source.contains("PREFERENCE: wait-for-settle is best"));
        assertTrue(source.contains("PREFERENCE: perform-kg-action over wait-for-settle"));
        assertTrue(source.contains("PREFERENCE: wait-for-settle over select-config"));
        assertFalse(source.contains("PREFERENCE: select-config over wait-for-settle"));
    }

    @Test
    void configurationSearchUsesDeterministicOrderingAndSkipsDisabledDevices() throws IOException {
        final String source = Files.readString(SOURCE);

        assertTrue(source.contains("light-processing*prefer*config-action-l1-over-b1"));
        assertTrue(source.contains("light-processing*prefer*config-action-l1-over-b2"));
        assertTrue(source.contains("light-processing*prefer*config-action-l2-over-b2"));
        assertTrue(source.contains("light-processing*prefer*abandon-l1-over-b1"));
        assertTrue(source.contains("light-processing*prefer*abandon-l1-over-b2"));
        assertTrue(source.contains("light-processing*prefer*abandon-l2-over-b2"));
        assertTrue(source.contains("light-processing*propose*abandon-disabled-config-b1"));
        assertTrue(source.contains("light-processing*prefer*disabled-abandon-over-config-action"));
        assertTrue(source.contains("-^reason disabled"));
    }

    private static int count(String haystack, String needle) {
        int result = 0;
        int offset = 0;

        while ((offset = haystack.indexOf(needle, offset)) >= 0) {
            result++;
            offset += needle.length();
        }

        return result;
    }
}
