package soar.rhs;

import org.jsoar.kernel.Agent;
import org.jsoar.kernel.memory.Wme;
import org.jsoar.kernel.rhs.functions.RhsFunctionContext;
import org.jsoar.kernel.rhs.functions.RhsFunctionException;
import org.jsoar.kernel.rhs.functions.RhsFunctionHandler;
import org.jsoar.kernel.symbols.Identifier;
import org.jsoar.kernel.symbols.Symbol;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class PrintList implements RhsFunctionHandler {

    Agent agent = null;

    public void setAgent(Agent agent){
        this.agent = agent;
        this.agent.getRhsFunctions().registerHandler(this);
    }

    @Override
    public String getName() {
        return "print-list";
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
        System.out.println("print list");
        Symbol s1 = arguments.get(0);
        Symbol s2 = arguments.get(1);
        List<Symbol> l = new ArrayList<>();
        Set<Wme> wmes = this.agent.getAllWmesInRete();
        for (Wme wme: wmes){
            //System.out.println("print wme: "+wme);
            if (wme.getIdentifier().equals(s1) && wme.getAttribute().equals(s2)){
                l.add(wme.getValue());
            }
        }
        System.out.println("list to print: " + s1 + " with param "+ s2 + " and value: "+l);
        return null;
    }
}
