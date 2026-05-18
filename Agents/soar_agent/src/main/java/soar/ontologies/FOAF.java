package soar.ontologies;

import org.eclipse.rdf4j.model.Resource;
import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;

public class FOAF {

    private static ValueFactory rdf = SimpleValueFactory.getInstance();

    public static Resource Agent = rdf.createIRI("http://xmlns.com/foaf/0.1/Agent");

    public static Resource Person = rdf.createIRI("http://xmlns.com/foaf/0.1/Person");
}
