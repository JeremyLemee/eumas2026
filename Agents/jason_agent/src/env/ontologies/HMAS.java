package ontologies;

import org.eclipse.rdf4j.model.IRI;
import org.eclipse.rdf4j.model.ValueFactory;
import org.eclipse.rdf4j.model.impl.SimpleValueFactory;

public class HMAS{

    private static ValueFactory rdf = SimpleValueFactory.getInstance();

    public static IRI Signifier = rdf.createIRI("https://purl.org/hmas/Signifier");

    public static IRI Annotation = rdf.createIRI("https://purl.org/hmas/Annotation");

    public static IRI recommendsAbility = rdf.createIRI("https://purl.org/hmas/recommendsAbility");

    public static IRI signifies = rdf.createIRI("https://purl.org/hmas/signifies");

    public static IRI conveys = rdf.createIRI("https://purl.org/hmas/conveys");

    public static IRI hasGoal = rdf.createIRI("https://purl.org/hmas/hasGoal");

    public static IRI Agent = rdf.createIRI("https://purl.org/hmas/Agent");

    public static IRI hasAbility = rdf.createIRI("https://purl.org/hmas/hasAbility");

    public static IRI hasInteractionPolicy = rdf.createIRI("https://purl.org/hmas/hasInteractionPolicy");

    public static IRI RecurrentPolicy = rdf.createIRI("https://purl.org/hmas/RecurrentPolicy");

    public static IRI hasAnnotationUrl = rdf.createIRI("https://purl.org/hmas/hasAnnotationUrl");

    public static IRI hasCallbackUrl = rdf.createIRI("https://purl.org/hmas/hasCallbackUrl");

    public static IRI MessagePolicy = rdf.createIRI("https://purl.org/hmas/MessagePolicy");

    public static IRI hasMessageUrl = rdf.createIRI("https://purl.org/hmas/hasMessageUrl");

    public static IRI hasId = rdf.createIRI("https://purl.org/hmas/hasId");

    public static IRI registerProfile = rdf.createIRI("https://purl.org/hmas/registerProfile");

    public static IRI queryAnnotations = rdf.createIRI("https://purl.org/hmas/queryAnnotations");

    public static IRI isProfileOf = rdf.createIRI("https://purl.org/hmas/isProfileOf");

    public static IRI Message = rdf.createIRI("https://purl.org/hmas/Message");

    public static IRI hasSender = rdf.createIRI("https://purl.org/hmas/hasSender");

    public static IRI hasReceiver = rdf.createIRI("https://purl.org/hmas/hasReceiver");

}
