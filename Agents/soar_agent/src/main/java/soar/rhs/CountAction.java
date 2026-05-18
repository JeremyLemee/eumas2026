package soar.rhs;

import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;
import org.jsoar.kernel.Agent;
import org.jsoar.kernel.memory.Wme;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Symbol;

import java.util.List;
import java.util.Set;

public class CountAction implements RhsFunctionHandler {

    Agent agent = null;

    public void setAgent(Agent agent){
        this.agent = agent;
        this.agent.getRhsFunctions().registerHandler(this);
    }

    @Override
    public String getName() {
        return "count";
    }

    @Override
    public int getMinArguments() {
        return 2;
    }

    @Override
    public int getMaxArguments() {
        return 2;
    }

    @Override
    public boolean mayBeStandalone() {
        return false;
    }

    @Override
    public boolean mayBeValue() {
        return false;
    }

    @Override
    public Symbol execute(RhsFunctionContext context, List<Symbol> arguments) throws RhsFunctionException {
        Symbol s1 = arguments.get(0);
        Symbol s2 = arguments.get(1);
        int count = 0;
        Set<Wme> wmes = this.agent.getAllWmesInRete();
        for (Wme wme: wmes){
            if (wme.getIdentifier().equals(s1) && wme.getAttribute().equals(s2)){
                count += 1;
            }
        }
        return this.agent.getSymbols().createInteger(count);
    }
}
