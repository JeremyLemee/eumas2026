package soar.rhs;

import org.jsoar.kernel.Agent;
import org.jsoar.kernel.Production;
import org.jsoar.kernel.ProductionType;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;
import org.jsoar.kernel.tracing.Printer;

import java.io.FileWriter;
import java.io.IOException;
import java.io.StringWriter;
import java.util.List;

public class StorePm implements RhsFunctionHandler {

    private Agent agent = null;

    public void setAgent(Agent agent) {
        this.agent = agent;
        this.agent.getRhsFunctions().registerHandler(this);
    }

    @Override
    public String getName() {
        return "store-pm";
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
        try (FileWriter fileWriter = new FileWriter("output.soar")) {
            for (ProductionType type : new ProductionType[]{
                    ProductionType.USER,
                    ProductionType.DEFAULT,
                    ProductionType.CHUNK,
                    ProductionType.TEMPLATE
            }) {
                List<Production> productions = agent.getProductions().getProductions(type);
                for (Production production : productions) {
                    StringWriter sw = new StringWriter();
                    Printer printer = new Printer(sw);
                    production.print(printer, false);
                    printer.flush();
                    fileWriter.write(sw.toString());
                    fileWriter.write("\n\n");
                }
            }
            System.out.println("store-pm: procedural memory saved to output.soar");
        } catch (IOException e) {
            throw new RhsFunctionException("store-pm: failed to write output.soar: " + e.getMessage(), e);
        }
        return null;
    }
}
