1 2 3
# Tema 1 - RL (Implementare Switch)

## CAM Table
In cadrul acestui task am urmat pasii din pseudocod si mi-am creat urmatoarele functii:
- **is_unicast()** -> verifica daca o adresa MAC este adresa unicast sau nu dupa urmatoarele reguli:
    - Adresa MAC == adresa de **BROADCAST** (reprezentare in string a adresei mac de broadcast: FF:FF:FF:FF:FF:FF) => adresa MAC nu este **UNICAST**;
    - Daca primul octet al unei adrese MAC (sau ultimii 4 biti) reprezinta o valoare para => adresa MAC este de tip **UNICAST**;
    - Altfel, aceasta este de tip **MULTICAST** (primul octet este impar).
- **send_broadcast_flooding()** -> trimite un pachet pe toate interfetele switch-ului, mai putin pe cea de pe care a venit.

Totodata, am creat o tabela CAM (reprezentata printr-un dictionar cu asocieri intre adrese MAC si porturi) in care adaug mereu intrari in momentul in care primesc un nou cadru. Apoi, verific daca adresa destinatie este **UNICAST** (is_unicast()) caz in care verific daca exsita adresa destinatie in tabela CAM a switch-ului, urmand sa trimit pe portul corespunzator, altfel fac flooding pe toate porturile (send_broadcast_flooding). In cazul in care adresa MAC este de tip BROADCAST SAU MULTICAST la fel trimit cadrul pe toate porturile (send_broadcast_flooding()).

## VLAN
In cadrul acestui task am urmat indicatiile din cerinta si am creat cateva functii:
- **read_sw_config()** -> citeste fisierul de configuratie al switch-ului (in functie de switch_id), salvez prioritatea switch-ului si imi creez un map/dictionar cu asociere intre denumirile porturilor si modul portului (**Access/Trunk**)
- **tag_frame(), untag_frame()** -> dupa cum le spune si numele acestea creeaza fie un frame in care am tagul "**.1Q**", fie unul fara tag.

La inceput creez doua cadre pe baza datelor primite, unul cu tag si unul fara tag (lucru care ajuta in cazul unui flooding sau broadcast, deoarece nu mai modific pe loc cadrul pentru a-l trimite de fiecare data), cu ajutorul celor doua functii tag_frame(), untag_frame(). Apoi verific daca frame-ul meu a ajuns pe un port de tip access caz in care salvez vlan_id-ul portului, altfel in cazul in care acesta vine de pe un port trunk am deja salvat vlan_id-ul sursa. Mai departe, de fiecare data cand vreau sa trimit un frame pe o interfata fac urmatoarele verificari:
- Daca interfata pe care vreau sa trimit este de tip **TRUNK** trimit un frame cu tag-ul "**.1Q**";
- Daca interfata pe care vreau sa trimit este de tip **ACCESS** , verific daca vlan_id-ul sursa este acelasi cu vlan_id-ul destinatie si trimit un frame fara tag (fac aceasta verificare pentru ca switch-ul de layer 2 nu ruteaza pachete intre VLAN-uri).

## STP
In cadrul acestui task am urmat pseudocodul de initializare si de rulare a STP-ului din cerinta, am completat functia **send_bdpu_every_sec()** conform cerintei si am creat cateva functii ajutatoare:
- **create_bpdu_frame()** -> functie ce-mi creeaza un cadru ce encapsuleaza header-ul de LLC si BPDU, urmand ordinea antetelor si campurilor din cerinta:
    ```Python
    frame = struct.pack("!6s", MULTICAST)
    frame += struct.pack("!6s", get_switch_mac())
    frame += struct.pack("!H", 38)
    frame += struct.pack("!BBB", 0x42, 0x42, 0x03)
    frame += struct.pack("!HBB", 0x0000, 0x00, 0x00)
    frame += struct.pack("!B", 0x00)
    frame += struct.pack("!Q", root_id)
    frame += struct.pack("!I", root_path_cost_)
    frame += struct.pack("!Q", bridge_id)
    frame += struct.pack("!H", 0x0000)
    frame += struct.pack("!HHHH", 0, 20, 2, 15)
    ```
- **parse_bpdu_header()** -> functie care imi extrage root_bridge_id, root_path_cost si sender_bridge_id dintr-un frame BPDU.

La inceput cand primesc un frame verific daca adresa MAC destinatie este adresa **MULTICAST 01:80:C2:00:00:00** caz in care stiu ca acela este un cadru de STP (BPDU, trimis doar intre switch-uri). Apoi urmez pasii algoritmului din cerinta si modific daca este cazul root_bridge_id-ul, root_port-ul si root_path_cost-ul. Aceste variabile sunt declarate global deoarece le folosesc in interiorul functiei de send_bdpu_every_sec() pentru verificari constante daca switch-ul curent este root_bridge caz in care trimit in paralele pachete BPDU pentru a anunta acest lucru celorlalte switch-uri (functia fiind lansata in paralel pe un thread). Odata "rulat STP-ul" am retinut intr-un dictionar asocieri intre interfete si starile lor (**Designated/Blocked**), cu ajutorul carora stiu pe ce porturi pot sa trimit cadrele normale (Nu trimit pe porturile aflate in starea BLOCKED).
