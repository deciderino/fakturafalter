// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Fakturafalter-Mitwirkende
//
// Prüfdienst: prüft mehrere ZUGFeRD/Factur-X-PDFs mit Mustang in *einer* JVM (statt einer JVM je Datei).
//
//   java -cp fakturafalter-pruefdienst.jar<Trenner>Mustang-CLI-<V>.jar Pruefdienst < pfade.txt
//
// Liest Dateipfade (UTF-8, eine je Zeile) von der Standardeingabe und schreibt je Datei
//   ##FAKTURAFALTER-ANFANG <pfad>
//   <validation>…</validation>      (Prüfbericht von Mustang, enthält veraPDF für PDF/A-3)
//   ##FAKTURAFALTER-ENDE
// Fehler einer Datei landen als <validation><summary status="invalid"/><error …/></validation>.
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

import org.mustangproject.validator.ZUGFeRDValidator;

public class Pruefdienst {
    public static void main(String[] args) throws Exception {
        PrintStream aus = new PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), true, "UTF-8");
        System.setOut(System.err);   // Ausgaben der Bibliotheken nicht in den Bericht mischen
        BufferedReader ein = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String pfad;
        while ((pfad = ein.readLine()) != null) {
            pfad = pfad.strip();
            if (pfad.isEmpty()) continue;
            String bericht;
            try {
                ZUGFeRDValidator v = new ZUGFeRDValidator();
                v.disableNotices();
                bericht = v.validate(pfad);
            } catch (Throwable t) {
                bericht = "<validation><summary status=\"invalid\"/><error type=\"intern\">"
                        + maskieren(t.toString()) + "</error></validation>";
            }
            aus.println("##FAKTURAFALTER-ANFANG " + pfad);
            aus.println(bericht);
            aus.println("##FAKTURAFALTER-ENDE");
            aus.flush();
        }
    }

    private static String maskieren(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }
}
