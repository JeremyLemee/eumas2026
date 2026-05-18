package soar.rhs;

import org.jsoar.kernel.Agent;
import org.jsoar.kernel.memory.Wme;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;

import java.io.FileWriter;
import java.io.IOException;
import java.util.List;
import java.util.Set;

public class PrintWm implements RhsFunctionHandler {

    private Agent agent = null;

    public void setAgent(Agent agent) {
        this.agent = agent;
        this.agent.getRhsFunctions().registerHandler(this);
    }

    @Override
    public String getName() {
        return "print-wm";
    }

    @Override
    public int getMinArguments() {
        return 0;
    }

    @Override
    public int getMaxArguments() {
        return 0;
    }

    @Override
    public boolean mayBeStandalone() {
        return true;
    }

    @Override
    public boolean mayBeValue() {
        return false;
    }

    @Override
    public Symbol execute(RhsFunctionContext context, List<Symbol> arguments) throws RhsFunctionException {
        try (FileWriter fileWriter = new FileWriter("wm.txt")) {
            Set<Wme> wmes = this.agent.getAllWmesInRete();
            for (Wme wme : wmes) {
                fileWriter.write(wme.toString());
                fileWriter.write(System.lineSeparator());
            }
            System.out.println("print-wm: working memory saved to wm.txt");
        } catch (IOException e) {
            throw new RhsFunctionException("print-wm: failed to write wm.txt: " + e.getMessage(), e);
        }
        return null;
    }
}
